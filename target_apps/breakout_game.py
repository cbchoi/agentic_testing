import pygame
import sys

# [품질 결함 1] 물리 연산 오류: 공이 패들에 닿아도 각도 계산 없이 무조건 위로만 튕김
def calculate_reflection(ball_rect, paddle_rect):
    return -1

def run_game():
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    ball = pygame.Rect(200, 150, 10, 10)
    paddle = pygame.Rect(150, 280, 100, 10)
    ball_speed = [2, 2]

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        ball.x += ball_speed[0]
        ball.y += ball_speed[1]

        if ball.top <= 0 or ball.bottom >= 300: ball_speed[1] *= -1
        if ball.left <= 0 or ball.right >= 400: ball_speed[0] *= -1

        # 패들 충돌 시 결함 함수 호출
        if ball.colliderect(paddle):
            ball_speed[1] *= calculate_reflection(ball, paddle)

        screen.fill((0, 0, 0))
        pygame.draw.ellipse(screen, (255, 255, 255), ball)
        pygame.draw.rect(screen, (255, 255, 255), paddle)
        pygame.display.flip()
        # [품질 결함 2] clock.tick()이 없어 CPU를 100% 점유함 (성능 효율성 결함)

if __name__ == "__main__":
    run_game()