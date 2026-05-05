# TG Repost Bot 🤖

Telegram-бот для репоста видео/текста по каналам и запланированной отправки.

## Деплой на Railway

### 1. Переменные окружения (Railway → Variables)
| Переменная | Пример |
|---|---|
| `BOT_TOKEN` | `7123456789:AAF...` |
| `ADMIN_ID` | `123456789` |
| `TARGET_CHANNELS` | `@channel1,@channel2,-100123456789` |

### 2. Шаги
1. Загрузи репо на GitHub
2. Railway → New Project → Deploy from GitHub
3. Добавь переменные окружения
4. Settings → убедись что тип сервиса **Worker**
5. Deploy ✅

### 3. Обновление
```bash
git add . && git commit -m "update" && git push
```

## Использование
- `/start` — открыть меню
- **📤 Репост** — отправь видео с caption или текст
- **⏰ Запланировать** — введи дату/время, потом текст
- `/cancel` — отмена текущего действия
