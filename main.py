import pygame
import sys
import random
import math
import os

# тут лежат все наши главные настройки и цвета
screen_width = 1600
screen_height = 900
fps = 60
tile_size = 100

# цвета (rgb)
black = (0, 0, 0);
white = (255, 255, 255);
player_color = (0, 150, 255);
attack_color = (255, 200, 0);
enemy_color = (255, 0, 0);
boss_color = (150, 0, 150);
xp_color = (0, 255, 0);
health_color = (255, 50, 50);
hud_bg_color = (50, 50, 50);
button_hover_color = (100, 100, 100);
grid_color = (40, 40, 40);
star_color = (200, 200, 200);
orbital_color = (200, 0, 255);
aura_color = (255, 100, 0, 100);
projectile_color = (0, 200, 255)


# камера, которая следит за игроком, чтобы он всегда был в центре
class Camera:
    def __init__(self):
        # запоминаем, где мы находимся в мире и размеры экрана
        self.world_x = 0.0;
        self.world_y = 0.0;
        self.screen_width = screen_width;
        self.screen_height = screen_height
        self.half_width = screen_width // 2;
        self.half_height = screen_height // 2

    def update(self, target_world_x, target_world_y):
        # плавно движемся к цели (игроку)
        self.world_x += (target_world_x - self.world_x) * 0.1
        self.world_y += (target_world_y - self.world_y) * 0.1

    def apply_to_coords(self, world_x, world_y):
        # превращаем мировые координаты (например, 1000, 500) в экранные (например, 800, 450)
        screen_x = int(world_x - self.world_x + self.half_width);
        screen_y = int(world_y - self.world_y + self.half_height)
        return screen_x, screen_y

    def apply_to_rect(self, world_rect):
        # делаем то же самое, но для целого прямоугольника
        screen_x, screen_y = self.apply_to_coords(world_rect.x, world_rect.y)
        return pygame.Rect(screen_x, screen_y, world_rect.width, world_rect.height)

    def is_rect_on_screen(self, world_rect):
        # проверяем, видим ли мы вообще этот объект? (чтобы не рисовать лишнего)
        # создаем "рамку" чуть больше экрана, для запаса
        screen_world_rect = pygame.Rect(self.world_x - self.half_width - tile_size,
                                        self.world_y - self.half_height - tile_size, self.screen_width + tile_size * 2,
                                        self.screen_height + tile_size * 2)
        return screen_world_rect.colliderect(world_rect)


# зеленые шарики опыта, которые выпадают из врагов
class XPSphere(pygame.sprite.Sprite):
    def __init__(self, world_x, world_y, xp_value=1):
        # просто создаем шарик в нужном месте
        super().__init__()
        self.world_x = world_x;
        self.world_y = world_y;
        self.xp_value = xp_value;
        self.speed = 4
        self.image = pygame.Surface((10, 10));
        self.image.fill(xp_color)
        self.rect = self.image.get_rect(center=(self.world_x, self.world_y))

    def update(self, player_world_rect, magnet_radius):
        # если игрок близко (внутри "магнита"), летим к нему
        dx = player_world_rect.centerx - self.world_x;
        dy = player_world_rect.centery - self.world_y
        dist = max(1, (dx ** 2 + dy ** 2) ** 0.5)
        if dist < magnet_radius:
            self.world_x += (dx / dist) * self.speed;
            self.world_y += (dy / dist) * self.speed
        self.rect.center = (int(self.world_x), int(self.world_y))

    def draw(self, surface, camera):
        # рисуем себя, если камера нас видит
        if camera.is_rect_on_screen(self.rect):
            surface.blit(self.image, camera.apply_to_rect(self.rect))


# это "вспышка" от удара (мачете, молот), которая появляется, крутится и исчезает
class AnimatedAttackVisual(pygame.sprite.Sprite):
    def __init__(self, world_rect_center, base_image, damage, lifetime_ms=300, penetrating=True,
                 start_angle=0):
        # запоминаем картинку, урон, как долго жить и под каким углом появиться
        super().__init__()
        self.base_image = base_image;
        self.image = self.base_image
        self.rect = self.image.get_rect(center=world_rect_center)
        self.world_center = world_rect_center
        self.damage = damage;
        self.lifetime_ms = lifetime_ms
        self.creation_time = pygame.time.get_ticks()
        self.penetrating = penetrating;
        self.enemies_hit = set()  # список врагов, которых мы уже ударили (чтобы не бить дважды)

        self.current_angle = start_angle
        self.current_scale = 0.0

    def update(self):
        # тут вся анимация: рост, вращение и проверка, не пора ли исчезнуть
        elapsed = pygame.time.get_ticks() - self.creation_time
        if elapsed > self.lifetime_ms:
            # время вышло, удаляем себя
            self.kill();
            return

        progress = elapsed / self.lifetime_ms
        # анимация "ease-out": быстрый рост и плавное замедление
        self.current_scale = 1.0 - (1.0 - progress) ** 2
        # анимация: вращение
        self.current_angle += 15  # просто крутимся

        # применяем новый размер и угол к картинке
        self.image = pygame.transform.rotozoom(self.base_image, self.current_angle, self.current_scale)
        self.rect = self.image.get_rect(center=self.world_center)

    def draw(self, surface, camera):
        if camera.is_rect_on_screen(self.rect):
            surface.blit(self.image, camera.apply_to_rect(self.rect))


# один шарик, который летает вокруг игрока (оружие "сферы")
class OrbitalSprite(pygame.sprite.Sprite):
    def __init__(self, image, damage, angle_offset):
        super().__init__();
        self.image = image;
        self.world_x = 0;
        self.world_y = 0
        self.rect = self.image.get_rect(center=(self.world_x, self.world_y))
        self.damage = damage;
        self.angle_offset = angle_offset
        self.last_hit_enemies = {};  # чтобы не бить одного и того же врага 100 раз в секунду
        self.hit_cooldown = 1000

    def update_position(self, player_world_x, player_world_y, angle, orbit_radius):
        # оружие сказало нам, где быть, мы туда и встаем (с учетом общего угла и радиуса)
        total_angle = angle + self.angle_offset
        self.world_x = player_world_x + math.cos(total_angle) * orbit_radius
        self.world_y = player_world_y + math.sin(total_angle) * orbit_radius
        self.rect.center = (int(self.world_x), int(self.world_y))

    def can_hit_enemy(self, enemy):
        # проверяем, прошел ли "кулдаун" для этого конкретного врага
        current_time = pygame.time.get_ticks()
        if enemy not in self.last_hit_enemies:
            self.last_hit_enemies[enemy] = current_time;
            return True
        if current_time - self.last_hit_enemies[enemy] > self.hit_cooldown:
            self.last_hit_enemies[enemy] = current_time;
            return True
        return False

    def draw(self, surface, camera):
        if camera.is_rect_on_screen(self.rect):
            surface.blit(self.image, camera.apply_to_rect(self.rect))


# ледяной осколок, летящий в цель
class ProjectileSprite(pygame.sprite.Sprite):
    def __init__(self, image, world_x, world_y, target_enemy, freeze_duration):
        super().__init__();
        self.image = image
        self.world_x = world_x;
        self.world_y = world_y
        self.rect = self.image.get_rect(center=(self.world_x, self.world_y))
        self.target_enemy = target_enemy;
        self.freeze_duration = freeze_duration
        self.speed = 10.0
        # ...и вычисляем направление полета (вектор)
        dx = self.target_enemy.world_x - self.world_x;
        dy = self.target_enemy.world_y - self.world_y
        dist = max(1, (dx ** 2 + dy ** 2) ** 0.5)
        self.vx = (dx / dist) * self.speed;
        self.vy = (dy / dist) * self.speed
        self.lifetime = 3000;  # как долго снаряд живет, если не попал
        self.creation_time = pygame.time.get_ticks()

    def update(self):
        # просто летим вперед по прямой
        self.world_x += self.vx;
        self.world_y += self.vy
        self.rect.center = (int(self.world_x), int(self.world_y))
        # если летим слишком долго, исчезаем (вдруг враг умер)
        if pygame.time.get_ticks() - self.creation_time > self.lifetime:
            self.kill()

    def draw(self, surface, camera):
        if camera.is_rect_on_screen(self.rect):
            surface.blit(self.image, camera.apply_to_rect(self.rect))


# "шаблон" для всех видов оружия. сам по себе ничего не делает
class Weapon:
    def __init__(self, damage=0, cooldown_ms=0, area_size_tuple=(0, 0)):
        # общие для всех оружия параметры: урон, скорость атаки, размер
        self.damage = float(damage);
        self.cooldown_ms = float(cooldown_ms)
        self.area_width = area_size_tuple[0];
        self.area_height = area_size_tuple[1]
        self.last_attack_time = 0;
        self.level = 0;
        self.max_level = 5
        self.last_target_direction = (1, 0)  # куда бить, если врагов нет

    def find_nearest_enemies(self, player, enemy_group, num_to_find):
        # удобная функция для поиска ближайших врагов
        enemies_with_dist = []
        for enemy in enemy_group:
            dist = (player.world_x - enemy.world_x) ** 2 + (player.world_y - enemy.world_y) ** 2
            enemies_with_dist.append((dist, enemy))
        enemies_with_dist.sort(key=lambda t: t[0])
        return [enemy for dist, enemy in enemies_with_dist[:num_to_find]]

    def update(self, player, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref):
        # это главный "мозг" оружия. проверяет, пора ли атаковать
        current_time = pygame.time.get_ticks()
        if current_time - self.last_attack_time > self.cooldown_ms:
            self.last_attack_time = current_time
            self.attack(player, attack_group, assets, enemy_group, game_ref)

    def attack(self, player, attack_group, assets, enemy_group, game_ref):
        # а вот тут каждое оружие будет делать что-то свое
        pass


# мачете. бьет в сторону ближайшего врага
class Machete(Weapon):
    def __init__(self):
        super().__init__(damage=10, cooldown_ms=800, area_size_tuple=(120, 120))

    def attack(self, player, attack_group, assets, enemy_group, game_ref):
        # ищем врага, определяем направление
        targets = self.find_nearest_enemies(player, enemy_group, 1)
        if targets:
            target = targets[0];
            dx = target.world_x - player.world_x;
            dy = target.world_y - player.world_y
            dist = max(1, (dx ** 2 + dy ** 2) ** 0.5);
            vx, vy = (dx / dist), (dy / dist)
            self.last_target_direction = (vx, vy)
        else:
            # если врагов нет, бьем туда же, куда и в прошлый раз
            vx, vy = self.last_target_direction

        # считаем угол, чтобы красиво повернуть картинку удара
        angle_rad = math.atan2(-vy, vx);
        angle_deg = math.degrees(angle_rad)

        current_size = self.area_width * player.attack_radius_multiplier
        offset_distance = current_size * 0.4
        attack_center_x = player.world_x + vx * offset_distance;
        attack_center_y = player.world_y + vy * offset_distance

        # берем картинку мачете и нужный размер
        base_image = pygame.transform.scale(assets['weapon_machete'], (int(current_size), int(current_size)))

        # создаем ту самую "вспышку" удара с нужным углом
        AnimatedAttackVisual(
            (attack_center_x, attack_center_y),
            base_image,
            self.damage,
            lifetime_ms=300,
            start_angle=angle_deg,
            penetrating=True
        ).add(attack_group)
        game_ref.play_sound('swing')  # вжух!


# нож. похож на мачете, но быстрее, слабее и не бьет "насквозь"
class Knife(Weapon):
    def __init__(self):
        super().__init__(damage=5, cooldown_ms=300, area_size_tuple=(80, 80))

    def attack(self, player, attack_group, assets, enemy_group, game_ref):
        targets = self.find_nearest_enemies(player, enemy_group, 1)
        if targets:
            target = targets[0];
            dx = target.world_x - player.world_x;
            dy = target.world_y - player.world_y
            dist = max(1, (dx ** 2 + dy ** 2) ** 0.5);
            vx, vy = (dx / dist), (dy / dist)
            self.last_target_direction = (vx, vy)
        else:
            vx, vy = self.last_target_direction

        angle_rad = math.atan2(-vy, vx);
        angle_deg = math.degrees(angle_rad)

        current_size = self.area_width * player.attack_radius_multiplier
        offset_distance = current_size * 0.5
        attack_center_x = player.world_x + vx * offset_distance;
        attack_center_y = player.world_y + vy * offset_distance

        base_image = pygame.transform.scale(assets['weapon_knife'], (int(current_size), int(current_size)))

        AnimatedAttackVisual(
            (attack_center_x, attack_center_y),
            base_image,
            self.damage,
            lifetime_ms=150,
            start_angle=angle_deg,
            penetrating=False  # это значит, что он исчезнет после первого же попадания
        ).add(attack_group)
        game_ref.play_sound('swing')


# молот. медленный, но мощный и бьет "насквозь"
class Hammer(Weapon):
    def __init__(self):
        super().__init__(damage=25, cooldown_ms=2000, area_size_tuple=(180, 180))

    def attack(self, player, attack_group, assets, enemy_group, game_ref):
        targets = self.find_nearest_enemies(player, enemy_group, 1)
        if targets:
            target = targets[0];
            dx = target.world_x - player.world_x;
            dy = target.world_y - player.world_y
            dist = max(1, (dx ** 2 + dy ** 2) ** 0.5);
            vx, vy = (dx / dist), (dy / dist)
            self.last_target_direction = (vx, vy)
        else:
            vx, vy = self.last_target_direction

        angle_rad = math.atan2(-vy, vx);
        angle_deg = math.degrees(angle_rad)

        current_size = self.area_width * player.attack_radius_multiplier
        offset_distance = current_size * 0.3
        attack_center_x = player.world_x + vx * offset_distance;
        attack_center_y = player.world_y + vy * offset_distance

        base_image = pygame.transform.scale(assets['weapon_hammer'], (int(current_size), int(current_size)))

        AnimatedAttackVisual(
            (attack_center_x, attack_center_y),
            base_image,
            self.damage,
            lifetime_ms=500,
            start_angle=angle_deg,
            penetrating=True
        ).add(attack_group)
        game_ref.play_sound('swing')


# это не сами шарики, а "менеджер", который ими управляет
class OrbitalWeapon(Weapon):
    def __init__(self, persistent_attack_group, assets):
        super().__init__(damage=5)
        # сколько шариков и какой радиус на каждом уровне
        self.level_map = {1: (2, 100), 2: (3, 100), 3: (5, 120), 4: (6, 120), 5: (7, 130)}
        self.spheres = pygame.sprite.Group();
        # нам нужна ссылка на группу, чтобы добавлять шарики прямо туда
        self.spheres_group_ref = persistent_attack_group
        self.angle = 0.0;
        self.rotation_speed = 0.04;
        self.orbit_radius = 100
        self.assets = assets;
        self.level = 0;
        self.max_level = 5

    def update(self, player, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref):
        # здесь мы не атакуем, а просто постоянно крутим шарики
        self.angle += self.rotation_speed
        if self.angle > 2 * math.pi: self.angle -= 2 * math.pi
        current_radius = self.orbit_radius * player.attack_radius_multiplier
        # говорим каждому шарику, где он должен быть
        for sphere in self.spheres:
            sphere.update_position(player.world_x, player.world_y, self.angle, current_radius)

    def level_up(self):
        # при прокачке удаляем старые шарики и создаем новые (уже больше)
        if self.level >= self.max_level: return
        self.level += 1;
        num_spheres, self.orbit_radius = self.level_map[self.level]
        for s in self.spheres: s.kill()
        for i in range(num_spheres):
            angle_offset = (2 * math.pi / num_spheres) * i
            new_sphere = OrbitalSprite(self.assets['orbital'], self.damage, angle_offset)
            self.spheres.add(new_sphere);
            self.spheres_group_ref.add(new_sphere)


# огненный круг вокруг игрока, который постоянно дамажит
class AuraWeapon(Weapon):
    def __init__(self, persistent_attack_group):
        super().__init__(damage=2);
        self.level = 0;
        self.max_level = 5;
        self.radius = 100
        # создаем саму картинку-спрайт ауры
        self.aura_sprite = self.create_aura_sprite()
        self.aura_group_ref = persistent_attack_group;
        self.aura_group_ref.add(self.aura_sprite)
        self.last_hit_enemies = {};  # тоже с кулдауном на врага
        self.hit_cooldown = 1000

    def create_aura_sprite(self):
        # рисуем полупрозрачный круг нужного размера
        size = int(self.radius * 2);
        image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(image, aura_color, (self.radius, self.radius), self.radius)
        if hasattr(self, 'aura_sprite'):
            self.aura_sprite.image = image;
            self.aura_sprite.rect = image.get_rect()
            self.aura_sprite.parent_aura = self;
            return self.aura_sprite
        else:
            sprite = pygame.sprite.Sprite();
            sprite.image = image;
            sprite.rect = image.get_rect()
            sprite.parent_aura = self  # ссылка на "менеджера"

            # небольшой хак, чтобы спрайт мог сам себя рисовать (он же не в группе)
            def draw(surface, camera):
                if camera.is_rect_on_screen(sprite.rect):
                    surface.blit(sprite.image, camera.apply_to_rect(sprite.rect))

            sprite.draw = draw
            return sprite

    def can_hit_enemy(self, enemy):
        # та же логика "кулдауна", что и у орбит
        current_time = pygame.time.get_ticks()
        if enemy not in self.last_hit_enemies or current_time - self.last_hit_enemies[enemy] > self.hit_cooldown:
            self.last_hit_enemies[enemy] = current_time
            return True
        return False

    def update(self, player, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref):
        # просто следим, чтобы аура всегда была на игроке
        current_radius = self.radius * player.attack_radius_multiplier
        # если радиус (например, от бонуса) изменился, перерисовываем круг
        if self.aura_sprite.rect.width != int(current_radius * 2):
            self.radius = current_radius;
            self.create_aura_sprite()
        self.aura_sprite.rect.center = player.rect.center

    def level_up(self):
        # при прокачке увеличиваем урон, радиус и перерисовываем круг
        if self.level >= self.max_level: return
        self.level += 1;
        self.damage += 2;
        self.radius += 20
        self.create_aura_sprite()


# оружие, которое стреляет ледяными осколками
class ProjectileWeapon(Weapon):
    def __init__(self, projectile_group, assets):
        super().__init__(cooldown_ms=2000)
        self.level = 0;
        self.max_level = 5;
        self.projectiles_to_fire = 1
        self.freeze_duration = 1000;
        self.projectile_group_ref = projectile_group
        self.assets = assets

    def update(self, player, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref):
        # это уже "атакующее" оружие, так что проверяем кулдаун
        current_time = pygame.time.get_ticks()
        if current_time - self.last_attack_time > self.cooldown_ms:
            self.last_attack_time = current_time
            # ищем, в кого бы стрельнуть
            targets = self.find_nearest_enemies(player, enemy_group, self.projectiles_to_fire)
            if targets:
                game_ref.play_sound('projectile')
                # создаем по снаряду на каждую цель
                for target in targets:
                    new_projectile = ProjectileSprite(self.assets['projectile'], player.world_x, player.world_y, target,
                                                      self.freeze_duration)
                    self.projectile_group_ref.add(new_projectile)

    def level_up(self):
        # прокачка дает больше снарядов и увеличивает время заморозки
        if self.level >= self.max_level: return
        self.level += 1
        if self.level == 2: self.projectiles_to_fire = 2
        if self.level == 3: self.projectiles_to_fire = 3; self.freeze_duration = 1500
        if self.level == 4: self.projectiles_to_fire = 4
        if self.level == 5: self.projectiles_to_fire = 5; self.freeze_duration = 2000


# обычный враг-моб
class Enemy(pygame.sprite.Sprite):
    def __init__(self, world_x, world_y, image, health=20, speed=2, xp_reward=1, damage=10, score_value=10):
        super().__init__()
        self.world_x = world_x;
        self.world_y = world_y
        self.image = image;
        self.base_image = image  # запоминаем "чистую" картинку для разморозки
        self.rect = self.image.get_rect(center=(self.world_x, self.world_y))
        self.health = health;
        self.base_speed = speed;
        self.speed = speed
        self.xp_reward = xp_reward;
        self.damage = damage;
        self.score_value = score_value
        self.is_frozen = False;
        self.freeze_timer = 0

    def move_towards_player(self, player_world_rect):
        # если заморожен, стоим на месте
        if self.is_frozen: return
        # логика движения: просто идем к игроку по прямой
        dx = player_world_rect.centerx - self.world_x;
        dy = player_world_rect.centery - self.world_y
        dist = max(1, (dx ** 2 + dy ** 2) ** 0.5)
        self.world_x += (dx / dist) * self.speed;
        self.world_y += (dy / dist) * self.speed
        self.rect.center = (int(self.world_x), int(self.world_y))

    def take_damage(self, amount, xp_group):
        # получаем урон. если хп кончилось - умираем
        self.health -= amount
        if self.health <= 0:
            # смерть: создаем шарик опыта и удаляем себя
            if xp_group is not None:
                XPSphere(self.rect.centerx, self.rect.centery, xp_value=self.xp_reward).add(xp_group)
            self.kill()
            return self.score_value, True
        return 0, False

    def freeze(self, duration_ms):
        # нас заморозили! останавливаемся и "синеем"
        self.is_frozen = True;
        self.speed = 0
        frozen_surf = self.base_image.copy()
        # это как раз "посинение" картинки
        frozen_surf.fill(projectile_color, special_flags=pygame.BLEND_RGB_MULT)
        self.image = frozen_surf
        self.freeze_timer = pygame.time.get_ticks() + duration_ms

    def update(self, player_world_rect, xp_group):
        # в каждом кадре проверяем, не пора ли "разморозиться"
        if self.is_frozen and pygame.time.get_ticks() > self.freeze_timer:
            self.is_frozen = False;
            self.speed = self.base_speed
            self.image = self.base_image
        self.move_towards_player(player_world_rect)

    def draw(self, surface, camera):
        if camera.is_rect_on_screen(self.rect):
            surface.blit(self.image, camera.apply_to_rect(self.rect))


# босс. он как враг, но жирнее и сильнее
class Boss(Enemy):
    def __init__(self, world_x, world_y, image, health=200, speed=1, xp_reward=50, damage=40, score_value=500):
        super().__init__(world_x, world_y, image, health, speed, xp_reward, damage, score_value)

    def freeze(self, duration_ms):
        # босса нельзя заморозить полностью, только замедлить
        self.speed = self.base_speed * 0.5
        frozen_surf = self.base_image.copy()
        frozen_surf.fill(projectile_color, special_flags=pygame.BLEND_RGB_MULT)
        self.image = frozen_surf
        self.freeze_timer = pygame.time.get_ticks() + duration_ms


# это мы. наш персонаж
class Player(pygame.sprite.Sprite):
    def __init__(self, world_x, world_y, image, chosen_weapon):
        super().__init__()
        self.world_x = world_x;
        self.world_y = world_y
        self.image = image
        self.rect = self.image.get_rect(center=(self.world_x, self.world_y))
        self.speed = 5.0
        self.weapons = [chosen_weapon]  # список всего нашего оружия. начинаем с выбранного
        self.level = 1;
        self.current_xp = 0;
        self.xp_to_next_level = 10
        self.magnet_radius = 150.0
        self.max_health = 100.0;
        self.health = self.max_health
        self.last_hit_time = 0;  # чтобы после удара неуязвимость 1 секунду
        self.invincibility_duration = 1000
        self.attack_radius_multiplier = 1.0
        self.xp_multiplier = 1.0;
        self.xp_upgrade_level = 0
        self.game = None

    def move(self):
        # проверяем кнопки (wasd + стрелки) и двигаемся
        keys = pygame.key.get_pressed()
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: self.world_x -= self.speed
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: self.world_x += self.speed
        if keys[pygame.K_w] or keys[pygame.K_UP]: self.world_y -= self.speed
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: self.world_y += self.speed
        self.rect.center = (int(self.world_x), int(self.world_y))

    def update(self, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref):
        # главный апдейт игрока: двигаемся и говорим всему оружию обновиться
        self.move()
        for weapon in self.weapons:
            weapon.update(self, attack_group, persistent_attack_group, enemy_group, projectile_group, assets, game_ref)

    def draw(self, surface, camera):
        # рисуем себя. если мы неуязвимы - мигаем
        current_time = pygame.time.get_ticks()
        is_visible = True
        # вот тут логика мигания (каждые 100 мс то видно, то нет)
        if current_time - self.last_hit_time < self.invincibility_duration:
            if (current_time // 100) % 2 != 0:
                is_visible = False
        if is_visible:
            surface.blit(self.image, camera.apply_to_rect(self.rect))

    def gain_xp(self, amount):
        # получаем опыт и проверяем, не получили ли новый уровень
        effective_amount = amount * self.xp_multiplier
        self.current_xp += effective_amount
        level_up_occurred = False
        # ура, левел ап! (может быть несколько раз за 1 шарик)
        while self.current_xp >= self.xp_to_next_level:
            self.current_xp -= self.xp_to_next_level;
            self.level += 1
            self.xp_to_next_level = self.level * 10;
            level_up_occurred = True
        return level_up_occurred

    def heal(self, amount):
        self.health += amount
        if self.health > self.max_health: self.health = self.max_health

    def take_damage(self, amount):
        # получаем урон, если мы не неуязвимы
        current_time = pygame.time.get_ticks()
        if current_time - self.last_hit_time > self.invincibility_duration:
            self.health -= amount;
            self.last_hit_time = current_time
            if self.health <= 0:
                self.health = 0;
                return True  # игрок умер
        return False  # игрок жив


# это главный класс, который всем управляет. "мозг" игры
class Game:
    def __init__(self):
        # готовим игру к запуску: экран, часы, шрифты, звуки и т.д.
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("vampire-like ")
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_state = 'weapon_select'  # начинаем с экрана выбора оружия
        try:
            # пытаемся загрузить красивый шрифт, если не выйдет - берем стандартный
            self.font = pygame.font.SysFont("arial", 30);
            self.font_small = pygame.font.SysFont("arial", 22)
            self.font_large = pygame.font.SysFont("arial", 50);
            self.font_score = pygame.font.SysFont("arial", 40, bold=True)
        except:
            self.font = pygame.font.Font(None, 40);
            self.font_small = pygame.font.Font(None, 30)
            self.font_large = pygame.font.Font(None, 60);
            self.font_score = pygame.font.Font(None, 50)
        self.camera = Camera();
        self.stars = self.generate_stars(200)
        self.sounds = self.load_sounds();
        self.assets = self.load_assets()
        # создаем группы для всех спрайтов, чтобы ими было легко управлять
        self.attack_group = pygame.sprite.Group();
        self.persistent_attack_group = pygame.sprite.Group()
        self.projectile_group = pygame.sprite.Group();
        self.enemy_group = pygame.sprite.Group()
        self.xp_group = pygame.sprite.Group();
        self.player_sprite_group = pygame.sprite.GroupSingle()
        self.player = None
        self.last_spawn_time = 0;
        self.spawn_interval = 1000
        self.wave_start_time = 0;
        self.wave_duration = 30000;
        self.wave_number = 1
        self.base_enemy_health = 20.0;
        self.base_xp_drop = 1;
        self.base_score_value = 10
        self.upgrade_pool = [];
        self.current_upgrade_choices = [];
        self.upgrade_buttons = []
        self.score = 0
        self.start_weapon_buttons = []
        self.generate_start_weapon_buttons()
        self.passive_upgrade_pool = [];
        self.new_weapon_upgrade_pool = []
        self.bgm_volume = 0.5;
        self.sfx_volume = 0.5
        self.bgm_slider_rect = pygame.Rect(screen_width // 2 - 150, 350, 300, 20)
        self.sfx_slider_rect = pygame.Rect(screen_width // 2 - 150, 450, 300, 20)
        self.slider_being_dragged = None  # для ползунков громкости в меню паузы
        pygame.mixer.music.set_volume(self.bgm_volume)

    def load_assets(self):
        # загружаем все картинки (ассеты) из папки
        assets = {};
        assets_path = "assets"

        # хитрая функция: пытаемся загрузить картинку. если не найдем - создаем цветной квадрат
        def load_with_fallback(filename, size, color=white):
            filepath = os.path.join(assets_path, filename)
            try:
                image = pygame.image.load(filepath).convert_alpha()
                # 'slash' и 'weapon_' имеют свой базовый размер, не масштабируем их
                if 'slash' not in filename and 'weapon_' not in filename:
                    image = pygame.transform.scale(image, size)
                print(f"загружен ассет: {filepath}")
                return image
            except Exception as e:
                print(f"не удалось загрузить {filepath}: {e}. создан 'fallback'.")
                fallback = pygame.Surface(size);
                fallback.fill(color)
                return fallback

        assets['player'] = load_with_fallback('player.png', (100, 100), player_color)
        assets['enemy'] = load_with_fallback('enemy.png', (50, 50), enemy_color)
        assets['boss'] = load_with_fallback('boss.png', (150, 150), boss_color)
        assets['orbital'] = load_with_fallback('orbital.png', (20, 20), orbital_color)
        assets['projectile'] = load_with_fallback('projectile.png', (15, 15), projectile_color)

        assets['slash'] = load_with_fallback('slash.png', (100, 100), attack_color)

        assets['weapon_machete'] = load_with_fallback('weapon_machete.png', (120, 120), attack_color)
        assets['weapon_knife'] = load_with_fallback('weapon_knife.png', (80, 80), attack_color)
        assets['weapon_hammer'] = load_with_fallback('weapon_hammer.png', (180, 180), attack_color)

        assets['machete_icon'] = load_with_fallback('machete_icon.png', (100, 100), white)
        assets['knife_icon'] = load_with_fallback('knife_icon.png', (100, 100), white)
        assets['hammer_icon'] = load_with_fallback('hammer_icon.png', (100, 100), white)
        return assets

    def load_sounds(self):
        # загружаем музыку и все звуковые эффекты
        sounds = {};
        assets_path = "assets"
        try:
            pygame.mixer.music.load(os.path.join(assets_path, 'music.ogg'))
            print("загружена music.ogg")
        except Exception as e:
            print(f"не удалось загрузить music.ogg: {e}")

        def load_sfx(filename):
            filepath = os.path.join(assets_path, filename)
            try:
                sound = pygame.mixer.Sound(filepath)
                print(f"загружен звук: {filepath}")
                return sound
            except Exception as e:
                print(f"не удалось загрузить {filepath}: {e}")
                return None

        sounds['swing'] = load_sfx('swing.wav');
        sounds['hit_enemy'] = load_sfx('hit_enemy.wav')
        sounds['hit_player'] = load_sfx('hit_player.wav');
        sounds['xp_pickup'] = load_sfx('xp_pickup.wav')
        sounds['level_up'] = load_sfx('level_up.wav');
        sounds['projectile'] = load_sfx('projectile.wav')
        sounds['pause_in'] = load_sfx('pause_in.wav');
        sounds['pause_out'] = load_sfx('pause_out.wav')
        return sounds

    def play_sound(self, sound_name):
        # проигрываем звук с учетом текущей громкости эффектов
        if sound_name in self.sounds and self.sounds[sound_name]:
            sound = self.sounds[sound_name]
            sound.set_volume(self.sfx_volume)
            sound.play()

    def generate_stars(self, num_stars):
        # создаем звезды для фона с эффектом параллакса (разная "глубина")
        stars = []
        for _ in range(num_stars):
            stars.append(
                {'x': random.randint(-2000, 2000), 'y': random.randint(-2000, 2000), 'depth': random.uniform(0.1, 0.6)})
        return stars

    def draw_background(self):
        # рисуем фон: черный космос, звезды и сетку
        self.screen.fill(black)
        cam_x, cam_y = self.camera.world_x, self.camera.world_y
        for star in self.stars:
            # вот тут и есть параллакс. звезды с большей "глубиной" двигаются медленнее
            star_screen_x = (star['x'] - cam_x * star['depth']) % screen_width;
            star_screen_y = (star['y'] - cam_y * star['depth']) % screen_height
            if star_screen_x < 0: star_screen_x += screen_width
            if star_screen_y < 0: star_screen_y += screen_height
            pygame.draw.circle(self.screen, star_color, (int(star_screen_x), int(star_screen_y)), 2)

        # рисуем сетку, которая "едет" под ногами
        start_x, start_y = - (cam_x % tile_size) + self.camera.half_width, - (
                cam_y % tile_size) + self.camera.half_height
        num_tiles_x, num_tiles_y = screen_width // tile_size + 2, screen_height // tile_size + 2
        for i in range(num_tiles_x):
            x = start_x - self.camera.half_width + i * tile_size
            pygame.draw.line(self.screen, grid_color, (x, 0), (x, screen_height))
        for i in range(num_tiles_y):
            y = start_y - self.camera.half_height + i * tile_size
            pygame.draw.line(self.screen, grid_color, (0, y), (screen_width, y))

    def generate_start_weapon_buttons(self):
        # создаем три кнопки для стартового экрана
        self.start_weapon_buttons = []
        button_width, button_height = 300, 250
        total_width = (button_width * 3) + (50 * 2);
        start_x = (screen_width // 2) - (total_width // 2)
        start_y = (screen_height // 2) - (button_height // 2)
        button_data = [
            {'name': 'мачете', 'desc': ' сбалансированно ', 'weapon_class': Machete, 'icon_name': 'machete_icon'},
            {'name': 'нож', 'desc': ' быстрый и слабый', 'weapon_class': Knife, 'icon_name': 'knife_icon'},
            {'name': 'молот', 'desc': ' медленный и мощный ', 'weapon_class': Hammer,
             'icon_name': 'hammer_icon'},
        ]
        for i, data in enumerate(button_data):
            rect = pygame.Rect(start_x + i * (button_width + 50), start_y, button_width, button_height)
            data['rect'] = rect
            self.start_weapon_buttons.append(data)

    def start_game(self, chosen_weapon_class):
        # игрок выбрал оружие! создаем игрока, запускаем таймеры и музыку
        self.player = Player(0, 0, self.assets['player'], chosen_weapon_class())
        self.player.game = self;
        self.player_sprite_group.add(self.player)
        start_weapon_name = type(self.player.weapons[0]).__name__

        # список всех "пассивных" улучшений (скорость, хп, урон)
        self.passive_upgrade_pool = [
            {'id': 'speed_up', 'text': 'скорость игрока +10%'}, {'id': 'magnet_up', 'text': 'радиус магнита +20%'},
            {'id': 'max_health_up', 'text': 'макс. здоровье +20%'},
            {'id': 'heal_25', 'text': 'восстановить 25% здоровья'},
            {'id': 'radius_up', 'text': 'радиус атаки +20%'}, {'id': 'xp_gain_1', 'text': 'опыт +20% (ур. 1)'},
            {'id': 'start_weapon_damage_up', 'text': f'урон ({start_weapon_name}) +15%'},
            {'id': 'start_weapon_cooldown_down', 'text': f'перезарядка ({start_weapon_name}) -10%'},
        ]
        # список нового оружия, которое можно будет взять на 10-м уровне
        self.new_weapon_upgrade_pool = [
            {'id': 'orbital_1', 'text': 'сферы урона', 'class': OrbitalWeapon},
            {'id': 'aura_1', 'text': 'аура огня', 'class': AuraWeapon},
            {'id': 'projectile_1', 'text': 'ледяной осколок', 'class': ProjectileWeapon},
        ]
        self.wave_start_time = pygame.time.get_ticks()
        self.game_state = 'playing';
        self.score = 0
        self.camera.world_x = self.player.world_x;
        self.camera.world_y = self.player.world_y
        pygame.mixer.music.play(loops=-1)

    def draw_weapon_selection_screen(self):
        # рисуем тот самый стартовый экран с выбором оружия
        self.screen.fill(black)
        mouse_pos = pygame.mouse.get_pos()
        title_text = self.font_large.render("выберите стартовое оружие", True, white)
        self.screen.blit(title_text, (screen_width // 2 - title_text.get_width() // 2, 200))
        for data in self.start_weapon_buttons:
            rect = data['rect'];
            # подсвечиваем кнопку, если мышь на ней
            color = button_hover_color if rect.collidepoint(mouse_pos) else hud_bg_color
            pygame.draw.rect(self.screen, color, rect);
            pygame.draw.rect(self.screen, white, rect, 3)
            icon_surf = self.assets[data['icon_name']]
            icon_rect = icon_surf.get_rect(center=(rect.centerx, rect.y + 70))
            self.screen.blit(icon_surf, icon_rect)
            name_surf = self.font.render(data['name'], True, white);
            desc_surf = self.font_small.render(data['desc'], True, white)
            self.screen.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 150))
            self.screen.blit(desc_surf, (rect.centerx - desc_surf.get_width() // 2, rect.y + 190))

    def spawn_enemy(self):
        # создает одного врага за пределами экрана
        side = random.choice(['top', 'bottom', 'left', 'right'])
        spawn_distance_x, spawn_distance_y = self.camera.half_width + 100, self.camera.half_height + 100
        if side == 'top':
            x, y = self.camera.world_x + random.randint(-spawn_distance_x,
                                                        spawn_distance_x), self.camera.world_y - spawn_distance_y
        elif side == 'bottom':
            x, y = self.camera.world_x + random.randint(-spawn_distance_x,
                                                        spawn_distance_x), self.camera.world_y + spawn_distance_y
        elif side == 'left':
            x, y = self.camera.world_x - spawn_distance_x, self.camera.world_y + random.randint(-spawn_distance_y,
                                                                                                spawn_distance_y)
        else:
            x, y = self.camera.world_x + spawn_distance_x, self.camera.world_y + random.randint(-spawn_distance_y,
                                                                                                spawn_distance_y)
        Enemy(x, y, self.assets['enemy'], health=int(self.base_enemy_health), speed=2, xp_reward=self.base_xp_drop,
              damage=10, score_value=self.base_score_value * self.base_xp_drop).add(self.enemy_group)

    def spawn_boss(self):
        # создает босса (появляется редко)
        x, y = self.player.world_x, self.player.world_y
        boss_health, boss_xp = int(self.base_enemy_health * 10), self.base_xp_drop * 50
        Boss(x, y, self.assets['boss'], health=boss_health, speed=1, xp_reward=boss_xp, damage=40,
             score_value=500 * self.base_xp_drop).add(self.enemy_group)

    def update_spawner(self):
        # проверяет, не пора ли создать нового врага (по таймеру)
        current_time = pygame.time.get_ticks()
        if current_time - self.last_spawn_time > self.spawn_interval:
            self.last_spawn_time = current_time
            self.spawn_enemy()

    def update_wave_timer(self):
        # следит за временем волны. когда время выходит - волна +1
        current_time = pygame.time.get_ticks()
        time_elapsed = current_time - self.wave_start_time
        if time_elapsed > self.wave_duration:
            # каждые 10 волн враги становятся сильнее
            if self.wave_number % 10 == 0:
                self.base_enemy_health *= 1.5;
                self.base_xp_drop += 1
            wave_bonus_score = 100 * self.base_xp_drop;
            self.score += wave_bonus_score
            print(f"--- волна {self.wave_number} пройдена! бонус: +{wave_bonus_score} очков ---")
            self.wave_number += 1
            self.wave_start_time = current_time
            self.spawn_interval = max(100, self.spawn_interval * 0.9)  # враги спавнятся чуть быстрее
            if self.wave_number % 5 == 0:
                self.spawn_boss()  # и появляется босс

    def handle_collisions(self):
        # очень важная часть: проверяем все столкновения

        # 1. удары (мачете, молот) столкнулись с врагами
        hits = pygame.sprite.groupcollide(self.attack_group, self.enemy_group, False, False)
        sound_played_this_frame = False
        for attack_visual, enemy_list in hits.items():
            for enemy in enemy_list:
                # проверяем, что мы этого врага этим ударом еще не били
                if enemy not in attack_visual.enemies_hit:
                    points_gained, was_killed = enemy.take_damage(attack_visual.damage, self.xp_group)
                    if not sound_played_this_frame:
                        self.play_sound('hit_enemy');
                        sound_played_this_frame = True
                    self.score += points_gained
                    attack_visual.enemies_hit.add(enemy)
                    # если оружие не "пробивное" (нож), оно исчезает
                    if not attack_visual.penetrating:
                        attack_visual.kill();
                        break

        # 2. "постоянные" атаки (сферы, аура) столкнулись с врагами
        persistent_hits = pygame.sprite.groupcollide(self.persistent_attack_group, self.enemy_group, False, False,
                                                     pygame.sprite.collide_circle)
        for persistent_attack, enemy_list in persistent_hits.items():
            for enemy in enemy_list:
                if isinstance(persistent_attack, OrbitalSprite):
                    # тут используем их личный кулдаун на врага
                    if persistent_attack.can_hit_enemy(enemy):
                        points_gained, was_killed = enemy.take_damage(persistent_attack.damage, self.xp_group)
                        if not sound_played_this_frame:
                            self.play_sound('hit_enemy');
                            sound_played_this_frame = True
                        self.score += points_gained
                elif hasattr(persistent_attack, 'parent_aura'):
                    if persistent_attack.parent_aura.can_hit_enemy(enemy):
                        points_gained, was_killed = enemy.take_damage(persistent_attack.parent_aura.damage,
                                                                      self.xp_group)
                        if not sound_played_this_frame:
                            self.play_sound('hit_enemy');
                            sound_played_this_frame = True
                        self.score += points_gained

        # 3. снаряды (лед) столкнулись с врагами
        projectile_hits = pygame.sprite.groupcollide(self.projectile_group, self.enemy_group, True, False)
        for projectile, enemy_list in projectile_hits.items():
            if enemy_list:
                enemy = enemy_list[0];
                enemy.freeze(projectile.freeze_duration)  # замораживаем врага

        # 4. игрок столкнулся с опытом
        xp_hits = pygame.sprite.spritecollide(self.player, self.xp_group, True)
        if xp_hits:
            self.play_sound('xp_pickup')
        for sphere in xp_hits:
            # если опыта хватило на уровень - ставим игру на "паузу" (level_up)
            if self.player.gain_xp(sphere.xp_value):
                self.game_state = 'level_up';
                self.play_sound('level_up');
                self.generate_upgrade_choices()

        # 5. враги столкнулись с игроком
        enemy_collisions = pygame.sprite.groupcollide(self.enemy_group, self.player_sprite_group, False, False)
        for enemy, player_list in enemy_collisions.items():
            # если игрок умер - конец игры
            if self.player.take_damage(enemy.damage):
                self.game_state = 'game_over';
                self.play_sound('hit_player');
                pygame.mixer.music.stop()
                break
            else:
                # звук удара по игроку (только в момент первого удара)
                if self.player.last_hit_time == pygame.time.get_ticks():
                    self.play_sound('hit_player')

    def find_weapon_in_player(self, weapon_class):
        # ищет у игрока оружие определенного типа (например, "аура")
        for w in self.player.weapons:
            if isinstance(w, weapon_class):
                return w
        return None

    def generate_upgrade_choices(self):
        # решает, какие 3 улучшения предложить игроку

        # каждые 10 уровней предлагаем новое оружие (если есть)
        if self.player.level % 10 == 0:
            available_new_weapons = []
            player_weapon_types = [type(w) for w in self.player.weapons]
            for weapon_data in self.new_weapon_upgrade_pool:
                if weapon_data['class'] not in player_weapon_types:
                    available_new_weapons.append(weapon_data)
            if available_new_weapons:
                self.current_upgrade_choices = random.sample(available_new_weapons, min(len(available_new_weapons), 3))
            else:
                # если все оружие уже есть, даем обычные улучшения
                self.generate_regular_upgrade_choices()
        else:
            # в остальное время - обычные улучшения
            self.generate_regular_upgrade_choices()

        # создаем кнопки для выбора
        self.upgrade_buttons = []
        button_width, button_height, start_y = 500, 80, 250
        for i in range(len(self.current_upgrade_choices)):
            rect = pygame.Rect(screen_width // 2 - button_width // 2, start_y + i * (button_height + 20), button_width,
                               button_height)
            self.upgrade_buttons.append(rect)

    def generate_regular_upgrade_choices(self):
        # собирает список *всех* доступных улучшений (пассивки + прокачка оружия)
        available_upgrades = list(self.passive_upgrade_pool)

        # особая логика для прокачки "бонуса к опыту" (чтобы не дублировался)
        xp_level = self.player.xp_upgrade_level
        if xp_level > 0:
            available_upgrades = [u for u in available_upgrades if 'xp_gain_1' not in u['id']]
        if 0 <= xp_level < 10:
            next_level_id = f'xp_gain_{xp_level + 1}'
            if not any(d['id'] == next_level_id for d in available_upgrades if 'xp_gain' in d['id']):
                available_upgrades.append({'id': next_level_id, 'text': f'опыт +20% (ур. {xp_level + 1})'})
        elif xp_level >= 10:
            available_upgrades = [u for u in available_upgrades if 'xp_gain' not in u['id']]

        # например: если у нас есть сферы, добавляем в список "сферы ур. 2"
        orbital_weapon = self.find_weapon_in_player(OrbitalWeapon)
        if orbital_weapon:
            next_level = orbital_weapon.level + 1
            if next_level <= orbital_weapon.max_level:
                num, _ = orbital_weapon.level_map[next_level]
                available_upgrades.append(
                    {'id': f'orbital_{next_level}', 'text': f'сферы урона (ур. {next_level}: {num} шт)'})

        aura_weapon = self.find_weapon_in_player(AuraWeapon)
        if aura_weapon:
            next_level = aura_weapon.level + 1
            if next_level <= aura_weapon.max_level:
                available_upgrades.append({'id': f'aura_{next_level}', 'text': f'аура огня (ур. {next_level})'})

        projectile_weapon = self.find_weapon_in_player(ProjectileWeapon)
        if projectile_weapon:
            next_level = projectile_weapon.level + 1
            if next_level <= projectile_weapon.max_level:
                available_upgrades.append(
                    {'id': f'projectile_{next_level}', 'text': f'ледяной осколок (ур. {next_level})'})

        # из всего списка выбираем 3 случайных
        self.current_upgrade_choices = random.sample(available_upgrades, min(len(available_upgrades), 3))

    def apply_upgrade(self, upgrade_id):
        # игрок выбрал улучшение. применяем его

        # (тут много if/elif для каждого апгрейда)
        if upgrade_id == 'speed_up':
            self.player.speed *= 1.10
        elif upgrade_id == 'magnet_up':
            self.player.magnet_radius *= 1.20
        elif upgrade_id == 'max_health_up':
            self.player.max_health *= 1.20;
            self.player.heal(self.player.max_health * 0.20)
        elif upgrade_id == 'heal_25':
            self.player.heal(self.player.max_health * 0.25)
        elif upgrade_id == 'radius_up':
            self.player.attack_radius_multiplier *= 1.20
        elif 'xp_gain' in upgrade_id:
            self.player.xp_multiplier += 0.20;
            self.player.xp_upgrade_level += 1
        elif upgrade_id == 'start_weapon_damage_up':
            self.player.weapons[0].damage *= 1.15
        elif upgrade_id == 'start_weapon_cooldown_down':
            self.player.weapons[0].cooldown_ms *= 0.90

        # если это апгрейд орбит...
        elif 'orbital' in upgrade_id:
            weapon = self.find_weapon_in_player(OrbitalWeapon)
            # ...а у нас их нет (это ур. 1), то создаем
            if not weapon:
                weapon = OrbitalWeapon(self.persistent_attack_group, self.assets);
                self.player.weapons.append(weapon)
            # ...и говорим оружию прокачаться
            weapon.level_up()
        elif 'aura' in upgrade_id:
            weapon = self.find_weapon_in_player(AuraWeapon)
            if not weapon:
                weapon = AuraWeapon(self.persistent_attack_group);
                self.player.weapons.append(weapon)
            weapon.level_up()
        elif 'projectile' in upgrade_id:
            weapon = self.find_weapon_in_player(ProjectileWeapon)
            if not weapon:
                weapon = ProjectileWeapon(self.projectile_group, self.assets);
                self.player.weapons.append(weapon)
            weapon.level_up()

    def draw_hud(self):
        # рисуем весь интерфейс: хп, опыт, таймер, счет
        current_time = pygame.time.get_ticks();
        time_elapsed = current_time - self.wave_start_time;
        time_remaining = (self.wave_duration - time_elapsed) // 1000
        timer_text = self.font.render(f"время до конца волны: {time_remaining} с", True, white);
        self.screen.blit(timer_text, (screen_width - timer_text.get_width() - 10, 10))

        wave_text = self.font.render(f"волна: {self.wave_number}", True, white);
        self.screen.blit(wave_text, (10, 10))

        level_text = self.font.render(f"уровень: {self.player.level}", True, white);
        self.screen.blit(level_text, (10, 45))

        # полоска здоровья
        hp_bar_width, hp_bar_height, hp_bar_x, hp_bar_y = 300, 25, 10, 80
        # считаем процент здоровья для полоски хп
        hp_fill_percent = self.player.health / self.player.max_health;
        hp_fill_width = hp_bar_width * hp_fill_percent
        pygame.draw.rect(self.screen, hud_bg_color, (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height));
        pygame.draw.rect(self.screen, health_color, (hp_bar_x, hp_bar_y, hp_fill_width, hp_bar_height))
        hp_text = self.font.render(f"{int(self.player.health)} / {int(self.player.max_health)}", True, white)
        hp_text_x, hp_text_y = hp_bar_x + (hp_bar_width // 2) - (hp_text.get_width() // 2), hp_bar_y + (
                hp_bar_height // 2) - (hp_text.get_height() // 2)
        self.screen.blit(hp_text, (hp_text_x, hp_text_y))

        # полоска опыта
        xp_bar_width, xp_bar_height = screen_width - 20, 20;
        xp_bar_x, xp_bar_y = 10, screen_height - xp_bar_height - 10
        fill_percent = 0
        if self.player.xp_to_next_level > 0: fill_percent = self.player.current_xp / self.player.xp_to_next_level
        fill_width = xp_bar_width * fill_percent
        pygame.draw.rect(self.screen, hud_bg_color, (xp_bar_x, xp_bar_y, xp_bar_width, xp_bar_height));
        pygame.draw.rect(self.screen, xp_color, (xp_bar_x, xp_bar_y, fill_width, xp_bar_height))
        xp_text = self.font.render(f"{int(self.player.current_xp)} / {int(self.player.xp_to_next_level)}", True, white)
        text_x, text_y = screen_width // 2 - xp_text.get_width() // 2, xp_bar_y + (xp_bar_height // 2) - (
                xp_text.get_height() // 2)
        self.screen.blit(xp_text, (text_x, text_y))

        # счет
        score_text = self.font_score.render(f"счет: {self.score}", True, white)
        score_text_x, score_text_y = screen_width // 2 - score_text.get_width() // 2, 10
        self.screen.blit(score_text, (score_text_x, score_text_y))

    def update_slider(self, mouse_pos):
        # логика для ползунков громкости в меню паузы
        if self.slider_being_dragged == 'bgm':
            slider_rect = self.bgm_slider_rect
            click_x_relative = mouse_pos[0] - slider_rect.x
            volume = click_x_relative / slider_rect.width
            volume = max(0.0, min(1.0, volume))
            self.bgm_volume = volume
            pygame.mixer.music.set_volume(self.bgm_volume)
        elif self.slider_being_dragged == 'sfx':
            slider_rect = self.sfx_slider_rect
            click_x_relative = mouse_pos[0] - slider_rect.x
            volume = click_x_relative / slider_rect.width
            volume = max(0.0, min(1.0, volume))
            self.sfx_volume = volume

    def draw_pause_menu(self):
        # рисуем меню паузы (затемнение и ползунки)
        s = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA);
        s.fill((0, 0, 0, 150));
        self.screen.blit(s, (0, 0))
        pause_text = self.font_large.render("пауза", True, white)
        self.screen.blit(pause_text, (screen_width // 2 - pause_text.get_width() // 2, 250))

        # ползунок музыки
        bgm_text = self.font.render("музыка", True, white)
        self.screen.blit(bgm_text, (self.bgm_slider_rect.x, self.bgm_slider_rect.y - 40))
        pygame.draw.rect(self.screen, hud_bg_color, self.bgm_slider_rect)
        handle_x = self.bgm_slider_rect.x + (self.bgm_slider_rect.width * self.bgm_volume)
        handle_rect = pygame.Rect(handle_x - 10, self.bgm_slider_rect.y - 5, 20, 30)
        pygame.draw.rect(self.screen, white, handle_rect)

        # ползунок эффектов
        sfx_text = self.font.render("эффекты", True, white)
        self.screen.blit(sfx_text, (self.sfx_slider_rect.x, self.sfx_slider_rect.y - 40))
        pygame.draw.rect(self.screen, hud_bg_color, self.sfx_slider_rect)
        handle_x = self.sfx_slider_rect.x + (self.sfx_slider_rect.width * self.sfx_volume)
        handle_rect = pygame.Rect(handle_x - 10, self.sfx_slider_rect.y - 5, 20, 30)
        pygame.draw.rect(self.screen, white, handle_rect)

    def run(self):
        # главный цикл игры. он работает, пока self.running == true
        while self.running:
            mouse_pos = pygame.mouse.get_pos()

            # 1. обработка событий (нажатия клавиш, мышь, закрытие окна)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
                if event.type == pygame.KEYDOWN:
                    # эскейп ставит/снимает паузу
                    if event.key == pygame.K_ESCAPE:
                        if self.game_state == 'playing':
                            self.game_state = 'paused';
                            pygame.mixer.music.pause();
                            self.play_sound('pause_in')
                        elif self.game_state == 'paused':
                            self.game_state = 'playing';
                            pygame.mixer.music.unpause();
                            self.play_sound('pause_out')

                # если мы на экране выбора, ждем клика по кнопке
                if self.game_state == 'weapon_select':
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        for data in self.start_weapon_buttons:
                            if data['rect'].collidepoint(mouse_pos):
                                self.start_game(data['weapon_class']);
                                break

                # если мы на экране прокачки, ждем клика по апгрейду
                elif self.game_state == 'level_up':
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        for i, rect in enumerate(self.upgrade_buttons):
                            if rect.collidepoint(event.pos):
                                self.apply_upgrade(self.current_upgrade_choices[i]['id'])
                                self.game_state = 'playing';
                                self.current_upgrade_choices = [];
                                self.upgrade_buttons = []
                                break

                # если на паузе, смотрим, не двигает ли игрок ползунок
                elif self.game_state == 'paused':
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.bgm_slider_rect.collidepoint(mouse_pos):
                            self.slider_being_dragged = 'bgm'
                        elif self.sfx_slider_rect.collidepoint(mouse_pos):
                            self.slider_being_dragged = 'sfx'
                        self.update_slider(mouse_pos)
                    if event.type == pygame.MOUSEBUTTONUP:
                        self.slider_being_dragged = None
                    if event.type == pygame.MOUSEMOTION and self.slider_being_dragged:
                        self.update_slider(mouse_pos)

                # если игра кончилась, ждем r (рестарт) или q (выход)
                elif self.game_state == 'game_over':
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_r: self.__init__()  # перезапускаем игру
                        if event.key == pygame.K_q: self.running = False

            # 2. обновление логики (только если игра не на паузе)
            if self.game_state == 'playing':
                self.player.update(self.attack_group, self.persistent_attack_group, self.enemy_group,
                                   self.projectile_group, self.assets, self)
                self.attack_group.update();  # обновляем "вспышки" ударов
                self.projectile_group.update()  # двигаем снаряды
                self.enemy_group.update(self.player.rect, self.xp_group)  # двигаем врагов
                self.xp_group.update(self.player.rect, self.player.magnet_radius)  # двигаем опыт
                self.update_spawner();  # спавним врагов
                self.update_wave_timer();  # следим за волной
                self.handle_collisions()  # проверяем столкновения
                self.camera.update(self.player.world_x, self.player.world_y)  # двигаем камеру

            # 3. отрисовка (всегда, в любом состоянии игры)
            self.draw_background()

            # 4. отрисовка того, что поверх фона
            if self.game_state == 'weapon_select':
                self.draw_weapon_selection_screen()

            elif self.game_state in ['playing', 'level_up', 'game_over', 'paused']:
                # рисуем все игровые объекты
                for sphere in self.xp_group: sphere.draw(self.screen, self.camera)
                for enemy in self.enemy_group: enemy.draw(self.screen, self.camera)
                for attack in self.attack_group: attack.draw(self.screen, self.camera)
                for persistent_attack in self.persistent_attack_group:
                    persistent_attack.draw(self.screen, self.camera)
                for projectile in self.projectile_group:
                    projectile.draw(self.screen, self.camera)
                self.player_sprite_group.sprite.draw(self.screen, self.camera)
                self.draw_hud()

            if self.game_state == 'level_up':
                # поверх игры рисуем экран прокачки
                s = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA);
                s.fill((0, 0, 0, 150));
                self.screen.blit(s, (0, 0))
                title = "новое оружие!" if self.player.level % 10 == 0 and any(
                    'aura' in c['id'] or 'orbital' in c['id'] or 'projectile' in c['id'] for c in
                    self.current_upgrade_choices) else "level up! выберите улучшение:"
                lvl_up_text = self.font_large.render(title, True, white);
                self.screen.blit(lvl_up_text, (screen_width // 2 - lvl_up_text.get_width() // 2, 200))

                # рисуем кнопки выбора
                for i, rect in enumerate(self.upgrade_buttons):
                    color = button_hover_color if rect.collidepoint(mouse_pos) else hud_bg_color
                    pygame.draw.rect(self.screen, color, rect);
                    pygame.draw.rect(self.screen, white, rect, 3)
                    choice_text = self.current_upgrade_choices[i]['text'];
                    text_surf = self.font.render(choice_text, True, white)
                    self.screen.blit(text_surf, (rect.centerx - text_surf.get_width() // 2,
                                                 rect.centery - text_surf.get_height() // 2))

            elif self.game_state == 'paused':
                # поверх игры рисуем меню паузы
                self.draw_pause_menu()

            elif self.game_state == 'game_over':
                # поверх игры рисуем экран "конец игры"
                s = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA);
                s.fill((0, 0, 0, 200));
                self.screen.blit(s, (0, 0))
                game_over_text = self.font_large.render("игра окончена", True, health_color);
                final_score_text = self.font_large.render(f"итоговый счет: {self.score}", True, white);
                prompt_text = self.font.render("нажмите [r] для перезапуска или [q] для выхода", True, white)
                self.screen.blit(game_over_text, (screen_width // 2 - game_over_text.get_width() // 2, 350))
                self.screen.blit(final_score_text, (screen_width // 2 - final_score_text.get_width() // 2, 420))
                self.screen.blit(prompt_text, (screen_width // 2 - prompt_text.get_width() // 2, 500))

            # 5. показываем нарисованный кадр
            pygame.display.flip()

            # 6. ждем, чтобы было 60 кадров в секунду
            self.clock.tick(fps)

        pygame.quit()
        sys.exit()


# эта строка запускает игру, если мы запустили этот файл напрямую
if __name__ == "__main__":
    game = Game()
    game.run()