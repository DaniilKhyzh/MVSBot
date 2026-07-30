# MVSBot

A semi-automated Python application for monitoring the Ukrainian HSC electronic queue website (https://eqn.hsc.gov.ua/) and sending queue information via Telegram.

## Features

- Automated browser navigation using Playwright (Chromium)
- Manual authentication through ID.GOV.UA (required by design)
- Service and department selection (configurable via environment variables)
- Network interception to capture ticket information from API responses
- Telegram Bot API integration for notifications
- Configurable via environment variables
- Full type hints and logging
- Modular, clean architecture

## Technology Stack

- Python 3.12+
- Playwright (Chromium)
- python-dotenv
- httpx
- Logging
- Type hints

## Project Structure

```
MVSBot/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── logger.py          # Logging setup
│   ├── browser.py         # Browser management and navigation
│   ├── telegram.py        # Telegram notifications
│   └── main.py            # Application entry point
├── .env                   # Environment variables (not in repo)
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/MVSBot.git
   cd MVSBot
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on the example below:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   CHAT_ID=your_telegram_chat_id
   BASE_URL=https://eqn.hsc.gov.ua/
   SERVICE_ID=43
   DEPARTMENT_ID=43
   HEADLESS=true
   SLOW_MO=0
   LOGIN_INDICATOR=text="Особистий кабінет"
   SERVICE_SELECTION_LINK=text="Записатися на прийом"
   PROCEED_BUTTON=button:has-text("Дальше")
   SERVICE_CENTER_INDICATOR=text="Виберіть中心 обслуговування"
   TICKET_API_PATTERN=/api/v1/ticket
   POLLING_INTERVAL=5
   ```

   **Note:** Adjust the selectors if the website changes. You can inspect the page to find appropriate selectors.

## Usage

1. Start the application:
   ```bash
   python src/main.py
   ```

2. The application will:
   - Launch a Chromium browser
   - Navigate to the HSC website
   - Wait for you to complete the ID.GOV.UA authentication manually
   - After login, navigate to personal cabinet
   - Select service ID 43 and department ID 43 (configurable)
   - Proceed to the service center selection page
   - Intercept network requests to capture ticket information
   - Send the ticket information to your Telegram chat

3. Once a ticket is received, the application will exit (you can modify it to run continuously if desired).

## Important Notes

- **Authentication must be manual**: The application waits for you to complete the ID.GOV.UA login process in the browser window. Do not attempt to automate ID.GOV.UA login as it violates terms of service and security best practices.
- **Browser remains the source of truth**: The application does not attempt to recreate sessions or use exported cookies. All requests originate from the browser session.
- **Selectors may need updating**: If the HSC website changes its interface, you may need to update the selectors in the `.env` file.
- **Respect the website's terms of service**: Use this tool responsibly and avoid excessive requests that could overload the service.

## Configuration

All configuration is done through environment variables in the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot Token (required) | - |
| `CHAT_ID` | Telegram Chat ID (required) | - |
| `BASE_URL` | HSC website URL | `https://eqn.hsc.gov.ua/` |
| `SERVICE_ID` | Service ID to select | `43` |
| `DEPARTMENT_ID` | Department ID to select | `43` |
| `HEADLESS` | Run browser in headless mode | `true` |
| `SLOW_MO` | Slow down browser actions by ms (for debugging) | `0` |
| `LOGIN_INDICATOR` | CSS selector/text indicator of successful login | `text="Особистий кабінет"` |
| `SERVICE_SELECTION_LINK` | CSS selector/text for service selection link | `text="Записатися на прийом"` |
| `PROCEED_BUTTON` | CSS selector/text for proceed button | `button:has-text("Дальше")` |
| `SERVICE_CENTER_INDICATOR` | CSS selector/text indicating service center selection page | `text="Виберіть центр обслуговування"` |
| `TICKET_API_PATTERN` | Regex pattern to match ticket API endpoint | `/api/v1/ticket` |
| `POLLING_INTERVAL` | Seconds to wait between retry attempts | `5` |

## How It Works

1. **Browser Initialization**: Launches Chromium with Playwright.
2. **Navigation**: Goes to the HSC website.
3. **Manual Authentication**: Waits for you to complete ID.GOV.UA login.
4. **Navigation**: After login, navigates through the personal cabinet to select service and department.
5. **Interception**: Sets up network request interception to capture ticket API responses.
6. **Notification**: Sends ticket information via Telegram.

## Troubleshooting

- **No ticket received**: Check that the selectors match the website elements. Use browser dev tools to verify.
- **Authentication timeout**: Increase the timeout in the code if you need more time to log in manually.
- **Selector issues**: Update the CSS/text selectors in `.env` to match current website structure.
- **Browser not showing**: Set `HEADLESS=false` and `SLOW_MO=500` to see the browser actions.

## License

This project is for educational purposes only. Use at your own risk and ensure compliance with the website's terms of service.

---

*Developed with Claude Code*