# MVSBot

A semi-automated Python application for monitoring the Ukrainian HSC electronic queue website (https://eqn.hsc.gov.ua/) and sending queue information via Telegram.

## Features

- Automated browser navigation using Playwright (Chromium)
- Manual authentication through ID.GOV.UA (required by design)
- Service and department selection (configurable via environment variables)
- Continuous monitoring for appointment availability (checks every 45 seconds)
- API data extraction for department information and available dates
- Telegram Bot API integration for notifications
- Configurable via environment variables
- Full type hints and logging
- Modular, clean architecture
- Smart change detection (only notifies when data actually changes)
- Fixed Cyrillic character handling for button selectors

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
   DEPARTMENT_ID=93
   HEADLESS=false
   SLOW_MO=500
   LOGIN_INDICATOR='https://eqn.hsc.gov.ua/cabinet'
   CABINET_INDICATOR='https://eqn.hsc.gov.ua/cabinet'
   SERVICE_SELECTION_LINK='https://eqn.hsc.gov.ua/cabinet/queue'
   PROCEED_BUTTON=button:has-text("Дальше")
   SERVICE_CENTER_INDICATOR=text="Виберіть центр обслуговування"
   TICKET_API_PATTERN=/api/v2/equeue/days
   POLLING_INTERVAL=45
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
   - Select service ID and department ID (configurable via .env)
   - Proceed through the service selection flow:
     * Click "Записатись у чергу"
     * Wait for navigation to cabinet/queue page
     * Click "Практичний іспит"
     * Click "Практичний іспит на транспортному засобі навчального закладу"
     * Click "Так" confirmation
     * Click "категорія В" (Note: Uses correct Cyrillic character В, not Latin B)
   - Wait 45 seconds for page stabilization (prevents API rate limiting)
   - Fetch department and availability data from the API
   - Send formatted information via Telegram
   - Repeat the process every {POLLING_INTERVAL} seconds

3. The application runs continuously until manually stopped (Ctrl+C), only sending notifications when new appointment data is detected.

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
| `DEPARTMENT_ID` | Department ID to select | `93` |
| `HEADLESS` | Run browser in headless mode | `false` |
| `SLOW_MO` | Slow down browser actions by ms (for debugging) | `500` |
| `LOGIN_INDICATOR` | CSS selector/text indicator of successful login | `'https://eqn.hsc.gov.ua/cabinet'` |
| `CABINET_INDICATOR` | CSS selector/text indicating cabinet page | `'https://eqn.hsc.gov.ua/cabinet'` |
| `SERVICE_SELECTION_LINK` | CSS selector/text for service selection link | `'https://eqn.hsc.gov.ua/cabinet/queue'` |
| `PROCEED_BUTTON` | CSS selector/text for proceed button | `button:has-text("Дальше")` |
| `SERVICE_CENTER_INDICATOR` | CSS selector/text indicating service center selection page | `text="Виберіть центр обслуговування"` |
| `TICKET_API_PATTERN` | Regex pattern to match ticket API endpoint | `/api/v2/equeue/days` |
| `POLLING_INTERVAL` | Seconds to wait between checks | `45` |

## How It Works

1. **Browser Initialization**: Launches Chromium with Playwright.
2. **Navigation**: Goes to the HSC website.
3. **Manual Authentication**: Waits for you to complete ID.GOV.UA login.
4. **Navigation**: After login, navigates through the personal cabinet to select service and department.
5. **Service Selection Flow**: Executes the precise button-click sequence:
   - "Записатись у чергу" (Sign up for queue)
   - Waits for navigation to cabinet/queue page
   - "Практичний іспит" (Practical exam)
   - "Практичний іспит на транспортному засобі навчального закладу" (Practical test on educational vehicle)
   - "Так" (Yes) confirmation
   - "категорія В" (Category B) - Fixed to use correct Cyrillic character (В, not B)
6. **Stabilization Wait**: Waits 45 seconds after form submission to avoid API rate limiting (429 errors)
7. **Data Retrieval**: Fetches department information and available dates from:
   - `https://eqn.hsc.gov.ua/api/v2/equeue/departments?serviceId={SERVICE_ID}`
   - `https://eqn.hsc.gov.ua/api/v2/equeue/days?serviceId={SERVICE_ID}&departmentId={DEPARTMENT_ID}`
8. **Notification Processing**: 
   - Extracts department details (name, location, availability)
   - Parses available dates from ISO timestamps (converts YYYY-MM-DDTHH:MM:SS to YYYY-MM-DD)
   - Formats a clear, Telegram-compatible message
9. **Smart Notification**: Only sends updates when data actually changes compared to previous check
10. **Continuous Loop**: Repeats the entire process every {POLLING_INTERVAL} seconds

## Example Notification

When new appointment data is detected, you'll receive a Telegram message like:

```
🎟️ <b>Queue Update for MVS Bot</b>
Service ID: <b>43</b>
Department ID: <b>93</b>
Department: <b>ТСЦ МВС № 5342</b>
Available Dates: <b>2026-07-31, 2026-08-01, 2026-08-05</b>

<i>Monitoring for updates every 45 seconds...</i>
```

## Updated Features (v2.0)

- **Fixed Button Selector**: Corrected "категорія B" to "категорія В" (using proper Cyrillic В character)
- **Rate Limiting Prevention**: Added 45-second delay before API calls to prevent 429 Too Many Requests errors
- **Enhanced Date Parsing**: Properly extracts and formats dates from ISO timestamps (YYYY-MM-DDTHH:MM:SS → YYYY-MM-DD)
- **True Continuous Monitoring**: Application runs indefinitely, checking for updates at the configured interval
- **Change Detection Intelligence**: Only sends notifications when queue data actually changes (reduces alert fatigue)
- **Improved Telegram Formatting**: Uses only Telegram-supported HTML tags (<b>, <i>) to prevent parsing errors
- **Accurate API Endpoints**: Uses the correct v2 endpoints for department and days data

## Troubleshooting

- **No data received**: Check that the selectors match the website elements. Use browser dev tools to verify.
- **Authentication timeout**: Increase the timeout in the code if you need more time to log in manually.
- **Selector issues**: Update the CSS/text selectors in `.env` to match current website structure.
- **Browser not showing**: Set `HEADLESS=false` and `SLOW_MO=500` to see the browser actions.
- **429 Errors**: If you're getting rate limit errors, increase the POLLING_INTERVAL in your .env file.
- **Telegram errors**: Verify your BOT_TOKEN and CHAT_ID are correct in the .env file.
- **Button not found**: Double-check that the website uses exactly "категорія В" (Cyrillic В) text for the button.
- **No date information**: The API might not be returning available days data - check logs for raw API responses.

## Notes on Department ID

The default DEPARTMENT_ID is set to 93 in the example .env file, which corresponds to "ТСЦ МВС № 5342" in Полтавська область, Лубенський район, м. Кременчук. You should adjust this value in your .env file to match the specific department you're interested in monitoring.

## License

This project is for educational purposes only. Use at your own risk and ensure compliance with the website's terms of service.

---

*Developed with Claude Code*