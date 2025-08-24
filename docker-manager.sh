#!/bin/bash

# Скрипт для управления Docker контейнерами Flibusta бота

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
print_message() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка наличия Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker не установлен. Установите Docker и попробуйте снова."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker не установлен. Установите Docker и попробуйте снова."
        exit 1
    fi
    
            print_success "Docker найден"
}

# Проверка наличия .env файла
check_env() {
    if [ ! -f .env ]; then
        print_warning "Файл .env не найден. Создаю на основе env_example.txt..."
        if [ -f env_example.txt ]; then
            cp env_example.txt .env
            print_warning "Файл .env создан. Отредактируйте его и добавьте свои данные!"
            exit 1
        else
            print_error "Файл env_example.txt не найден. Создайте .env файл вручную."
            exit 1
        fi
    fi
    
    print_success "Файл .env найден"
}

# Создание директории для данных
create_data_dir() {
    if [ ! -d data ]; then
        mkdir -p data
        print_message "Создана директория data для базы данных"
    fi
}

# Функция запуска
start() {
    print_message "Запуск Flibusta бота..."
    check_docker
    check_env
    create_data_dir
    
    docker compose up -d
            print_success "Бот запущен! Проверьте логи: docker compose logs -f"
}

# Функция остановки
stop() {
    print_message "Остановка Flibusta бота..."
    docker compose down
    print_success "Бот остановлен"
}

# Функция перезапуска
restart() {
    print_message "Перезапуск Flibusta бота..."
    docker compose restart
    print_success "Бот перезапущен"
}

# Функция просмотра логов
logs() {
    print_message "Показ логов бота..."
    docker compose logs -f
}

# Функция сборки
build() {
    print_message "Сборка Docker образа..."
    check_docker
    docker compose build --no-cache
    print_success "Образ собран"
}

# Функция очистки
clean() {
    print_message "Очистка Docker ресурсов..."
    docker compose down -v --remove-orphans
    docker system prune -f
    print_success "Очистка завершена"
}

# Функция статуса
status() {
    print_message "Статус контейнеров..."
    docker compose ps
}

# Функция обновления
update() {
    print_message "Обновление бота..."
    docker compose pull
    docker compose up -d --build
    print_success "Бот обновлен"
}

# Функция помощи
help() {
    echo "Использование: $0 {start|stop|restart|logs|build|clean|status|update|help}"
    echo ""
    echo "Команды:"
    echo "  start   - Запустить бота"
    echo "  stop    - Остановить бота"
    echo "  restart - Перезапустить бота"
    echo "  logs    - Показать логи"
    echo "  build   - Собрать Docker образ"
    echo "  clean   - Очистить Docker ресурсы"
    echo "  status  - Показать статус контейнеров"
    echo "  update  - Обновить бота"
    echo "  help    - Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 start    # Запустить бота"
    echo "  $0 logs     # Показать логи"
    echo "  $0 stop     # Остановить бота"
}

# Основная логика
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    build)
        build
        ;;
    clean)
        clean
        ;;
    status)
        status
        ;;
    update)
        update
        ;;
    help|--help|-h)
        help
        ;;
    *)
        print_error "Неизвестная команда: $1"
        echo ""
        help
        exit 1
        ;;
esac
