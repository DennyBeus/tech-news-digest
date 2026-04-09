# Задача: ежедневный дайджест multi-parser

Ты — scheduled агент. Твоя задача: сформировать ежедневный дайджест AI-новостей из базы данных проекта multi-parser и отправить его в Telegram.

## Шаги (выполняй строго по порядку)

### 1. Экспорт статей из БД

Запусти скрипт:

```bash
cd ~/deploy/multi-parser && python3 scripts/delivery/export-latest.py --hours 24 --min-score 6 --top-n 100 --output /tmp/digest-raw.md
```

Скрипт выведет markdown с топ-статьями за последние 24 часа.

### 2. Прочитай экспортированный файл

Прочитай `/tmp/digest-raw.md` — это список статей с заголовками, ссылками и скором.

### 3. Напиши переведённый дайджест

Создай файл `/tmp/digest-final.md` со следующей структурой:

- Заголовок: `# Tech Digest — <дата UTC>`
- Подзаголовок: `> Статьи за 24ч | Отобрано: N | Скор >= 6`
- Разделы по источникам (GitHub Trending, GitHub, Reddit, Twitter/X, RSS, Web)
- Для каждой статьи: переведённый на русский заголовок + ссылка + score + источник
- Технические термины (LLM, AI, ML, GPU, API, open-source, benchmark, fine-tuning, inference, token, model, agent и т.п.) оставляй на английском
- Имена людей и компаний не переводи
- Если есть snippet — переведи и добавь (не более 2 предложений)

### 4. Сгенерируй PDF

```bash
cd ~/deploy/multi-parser && python3 scripts/delivery/generate-pdf.py --input /tmp/digest-final.md --output /tmp/digest-final.pdf
```

### 5. Отправь PDF в Telegram

Используй Telegram MCP reply tool:
- chat_id: `546745364`
- text: краткое сообщение, например: `Дайджест за <дата>. Отобрано N статей (скор >= 6).`
- files: `["/tmp/digest-final.pdf"]`

## Правила

- Если export-latest.py вернул 0 статей — отправь текстовое сообщение в Telegram: "Дайджест за <дата>: нет новых статей с качеством >= 6 за последние 24ч."
- Не придумывай статьи — только то что есть в /tmp/digest-raw.md
- Не меняй ссылки
- Если generate-pdf.py упал с ошибкой — отправь markdown-текст напрямую в Telegram (первые 4000 символов)
