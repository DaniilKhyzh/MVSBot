import asyncio
import json
import re
from typing import Optional, Pattern

from playwright.async_api import Page, Route, async_playwright

from .config import settings
from .logger import logger


class BrowserManager:
    """Manages the Playwright browser and navigation."""

    def __init__(self) -> None:
        self.browser = None
        self.page: Optional[0] = None
        self.page = None
        self.previous_queue_data: Optional[dict] = None  # To store previous queue data for comparison

    async def start(self) -> None:
        """Launch the browser and create a new page."""
        logger.info("Launching browser...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=settings.headless,
            slow_mo=settings.slow_mo,
        )
        # Create a new page
        self.page = await self.browser.new_page()
        logger.info("Browser started.")

    async def stop(self) -> None:
        """Close the browser and clean up."""
        if self.browser:
            await self.browser.close()
            logger.info("Browser stopped.")

    async def wait_for_login(self) -> None:
        """Wait for the user to complete ID.GOV.UA authentication manually."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Waiting for user to log in via ID.GOV.UA...")
        # Wait for an element that indicates the user is logged in.
        # This is a placeholder selector; the user may need to adjust it.
        # Common indicators: a link with text like "Особистий кабінет" or a user icon.
        login_indicator = settings.login_indicator
        try:
            # Check if indicator is a URL pattern
            if login_indicator.startswith("http://") or login_indicator.startswith("https://"):
                # Wait for URL to match the pattern
                await self.page.wait_for_url(login_indicator, timeout=120000)  # 2 minutes
            else:
                # Wait for the login indicator to appear (user has logged in)
                await self.page.wait_for_selector(login_indicator, timeout=120000)  # 2 minutes
            logger.info("User logged in successfully.")
        except Exception as e:
            logger.error(f"Error while waiting for login: {e}")
            raise

    async def wait_for_cabinet_page(self) -> None:
        """Wait for the cabinet page to load after login."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Waiting for cabinet page to load...")
        # Wait for an element that indicates we're on the cabinet page.
        # This could be the same as login indicator or different.
        cabinet_indicator = settings.cabinet_indicator
        try:
            # Check if indicator is a URL pattern
            if cabinet_indicator.startswith("http://") or cabinet_indicator.startswith("https://"):
                # Wait for URL to match the pattern
                await self.page.wait_for_url(cabinet_indicator, timeout=15000)
            else:
                # Wait for the cabinet indicator to appear
                await self.page.wait_for_selector(cabinet_indicator, timeout=15000)
            logger.info("Cabinet page loaded.")
        except Exception as e:
            logger.error(f"Error while waiting for cabinet page: {e}")
            raise

    async def execute_service_selection_flow(self) -> None:
        """
        Execute the specific service selection flow as per user requirements:
        1. Click "Записатись у чергу" button
        2. Wait for navigation to cabinet/queue
        3. Click "Практичний іспит"
        4. Click "Практичний іспит на транспортному засобі навчального закладу"
        5. Click "Так" confirmation
        6. Click "категорія B"
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Starting service selection flow...")

        # Step 1: Click "Записатись у чергу" button
        logger.info('Clicking "Записатись у чергу" button')
        await self.page.click('text="Записатись у чергу"')
        # Wait for navigation to occur

        # Step 2: Wait for navigation to https://eqn.hsc.gov.ua/cabinet/queue
        logger.info('Waiting for navigation to cabinet/queue page')
        await self.page.wait_for_url('https://eqn.hsc.gov.ua/cabinet/queue', timeout=15000)
        logger.info("Successfully navigated to cabinet/queue page")

        # Step 3: Click "Практичний іспит"
        logger.info('Clicking "Практичний іспит" button')
        # Wait for the element to be visible and enabled
        await self.page.wait_for_selector('text="Практичний іспит"', state="visible", timeout=20000)
        await self.page.click('text="Практичний іспит"')

        # Step 4: Click "Практичний іспит на транспортному засобі навчального закладу"
        logger.info('Clicking "Практичний іспит на транспортному засобі навчального закладу" button')
        # Wait for the element to be visible and enabled
        await self.page.wait_for_selector('text="Практичний іспит на транспортному засобі навчального закладу"', state="visible", timeout=20000)
        await self.page.click('text="Практичний іспит на транспортному засобі навчального закладу"')

        # Step 5: Click confirmation button with text "Так"
        logger.info('Clicking confirmation button "Так"')
        # Wait for the element to be visible and enabled
        await self.page.wait_for_selector('text="Так"', state="visible", timeout=20000)
        await self.page.click('text="Так"')


        # Step 6: Click "категорія В"
        logger.info('Clicking "категорія В" button')
        # Wait for the element to be visible and enabled
        await self.page.wait_for_selector('text="категорія В"', state="visible", timeout=20000)
        await self.page.click('text="категорія В"')

        logger.info("Service selection flow completed successfully")

    async def get_queue_data(self) -> Optional[dict]:
        """
        Fetch queue data by making two API requests using the authenticated browser session:
        1. GET /api/v2/equeue/days?serviceId=43&departmentId=93 to get available dates
        2. For each date, GET /api/v2/equeue/slots?serviceId=43&departmentId=93&date=<date> to get time slots

        This approach uses Playwright's request functionality which maintains the
        authenticated browser session, ensuring we have the same cookies and permissions
        as if we were making the requests from the page itself.

        Returns:
            Queue data dictionary if successful, None otherwise.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        try:
            logger.info("Fetching queue data via authenticated API requests...")

            # Get the target department ID and service ID from settings
            target_department_id = int(settings.department_id)
            service_id = settings.service_id

            # Step 1: Fetch available dates
            logger.info(f"Fetching days for service {service_id}, department {target_department_id}")
            days_response = await self.page.request.fetch(
                f"https://eqn.hsc.gov.ua/api/v2/equeue/days?serviceId={service_id}&departmentId={target_department_id}",
                method="GET",
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
                    "referer": "https://eqn.hsc.gov.ua/",
                },
                timeout=30000  # 30 seconds timeout
            )

            if not days_response.ok:
                logger.error(f"Failed to fetch days data: {days_response.status} {days_response.status_text}")
                # Return basic structure even if we can't get days
                return {
                    "department": {"id": target_department_id},
                    "available_slots": [],
                    "service_id": service_id,
                    "department_id": target_department_id
                }

            days_data = await days_response.json()
            # Extract data array if wrapped
            if isinstance(days_data, dict) and "data" in days_data:
                days_data = days_data["data"]

            logger.info(f"Received days data with {len(days_data) if isinstance(days_data, list) else 0} entries")

            # Step 2: For each date, fetch time slots
            available_slots = []
            if isinstance(days_data, list):
                for day_item in days_data:
                    if isinstance(day_item, dict) and 'date' in day_item:
                        date_str = day_item['date']
                        # Extract date part from ISO timestamp (YYYY-MM-DD)
                        if 'T' in date_str:
                            date_only = date_str.split('T')[0]
                        else:
                            date_only = date_str

                        # Fetch time slots for this date
                        slots_response = await self.page.request.fetch(
                            f"https://eqn.hsc.gov.ua/api/v2/equeue/slots?serviceId={service_id}&departmentId={target_department_id}&date={date_only}",
                            method="GET",
                            headers={
                                "accept": "application/json, text/plain, */*",
                                "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
                                "referer": "https://eqn.hsc.gov.ua/",
                            },
                            timeout=30000  # 30 seconds timeout
                        )

                        times = []
                        if slots_response.ok:
                            slots_data = await slots_response.json()
                            # Handle different possible response formats
                            if isinstance(slots_data, list):
                                times = slots_data
                            elif isinstance(slots_data, dict) and "data" in slots_data:
                                times = slots_data["data"]
                            else:
                                logger.warning(f"Unexpected slots data format for date {date_only}: {slots_data}")
                        else:
                            logger.error(f"Failed to fetch slots for date {date_only}: {slots_response.status} {slots_response.status_text}")

                        available_slots.append({
                            "date": date_only,
                            "times": times
                        })
                    else:
                        logger.warning(f"Unexpected day item format: {day_item}")

            result = {
                "department": {"id": target_department_id},
                "available_slots": available_slots,
                "service_id": service_id,
                "department_id": target_department_id
            }
            return result

        except Exception as e:
            logger.error(f"Error fetching queue data: {e}")
            return None

    async def run_workflow(self) -> Optional[dict]:
        """
        Run the complete workflow: start browser, navigate to cabinet,
        execute service selection flow, and get queue data.

        Returns:
            Queue data dictionary if successful and updated, else None.
        """
        try:
            await self.start()
            assert self.page is not None

            # NAVIGATE TO BASE URL - wait for network idle to ensure page is ready
            logger.info(f"Navigating to {settings.base_url}")
            await self.page.goto(settings.base_url)
            await self.page.wait_for_load_state("networkidle", timeout=15000)

            # WAIT FOR LOGIN (ID.GOV.UA authentication)
            await self.wait_for_login()

            # WAIT FOR CABINET PAGE (after login)
            await self.wait_for_cabinet_page()

            # EXECUTE SERVICE SELECTION FLOW
            await self.execute_service_selection_flow()

            # Wait for page to stabilize after selection before fetching data
            # This helps avoid rate limiting (429 errors) from rapid requests
            logger.info("Waiting for page to stabilize before fetching queue data...")
            await asyncio.sleep(45)  # 45 seconds delay to avoid rate limiting

            # GET QUEUE DATA VIA DIRECT API CALL
            queue_data = await self.get_queue_data()

            if queue_data is None:
                logger.warning("Failed to retrieve queue data")
                return None

            # Check if data has changed
            if self.previous_queue_data != queue_data:
                logger.info("Queue data has changed!")
                self.previous_queue_data = json.loads(json.dumps(queue_data))  # Deep copy
                return queue_data
            else:
                logger.info("Queue data unchanged from previous check")
                return None  # Return None if no change, as per requirements

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            return None
        finally:
            await self.stop()