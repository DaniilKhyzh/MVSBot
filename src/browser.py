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
        Fetch queue data by making a direct API request to get department information
        for the selected service and department.

        Based on the CURL example in the user's message, the endpoint is:
        https://eqn.hsc.gov.ua/api/v2/equeue/departments?serviceId=43

        Returns:
            Queue data dictionary if successful, None otherwise.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        try:
            logger.info("Fetching queue data from API...")

            # Make request to get departments for the service
            # Using the page's request context to maintain authentication
            response = await self.page.request.fetch(
                f"https://eqn.hsc.gov.ua/api/v2/equeue/departments?serviceId={settings.service_id}",
                method="GET",
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
                    "referer": "https://eqn.hsc.gov.ua/",
                }
            )

            if not response.ok:
                logger.error(f"Failed to fetch department data: {response.status} {response.status_text}")
                return None

            departments_data = await response.json()
            logger.info(f"Received departments data: {departments_data}")

            # Find the specific department we're interested in
            target_department_id = int(settings.department_id)
            department_info = None

            # Handle different possible response formats
            departments = None
            if isinstance(departments_data, list):
                departments = departments_data
            elif isinstance(departments_data, dict):
                # Check if it's wrapped in a common structure
                if "data" in departments_data and isinstance(departments_data["data"], list):
                    departments = departments_data["data"]
                elif "departments" in departments_data and isinstance(departments_data["departments"], list):
                    departments = departments_data["departments"]
                else:
                    # Assume the dict itself contains the department info
                    departments = [departments_data]

            if departments:
                for dept in departments:
                    if isinstance(dept, dict):
                        dept_id = dept.get("id") or dept.get("departmentId") or dept.get("value")
                        if dept_id is not None and int(dept_id) == target_department_id:
                            department_info = dept
                            break

            if department_info is None:
                logger.warning(f"Could not find department {target_department_id} in response")
                # Return the whole response as fallback
                return departments_data

            # Now try to get more specific queue/day information for this department
            # Based on the user's curl example, we might want to check days/slots
            try:
                days_response = await self.page.request.fetch(
                    f"https://eqn.hsc.gov.ua/api/v2/equeue/days?serviceId={settings.service_id}&departmentId={target_department_id}",
                    method="GET",
                    headers={
                        "accept": "application/json, text/plain, */*",
                        "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
                        "referer": "https://eqn.hsc.gov.ua/",
                    }
                )

                if days_response.ok:
                    days_data = await days_response.json()
                    # Combine department info with days info
                    result = {
                        "department": department_info,
                        "available_days": days_data,
                        "service_id": settings.service_id,
                        "department_id": settings.department_id
                    }
                    return result
                else:
                    logger.warning(f"Could not fetch days data: {days_response.status}")
                    # Still return department info
                    return {
                        "department": department_info,
                        "service_id": settings.service_id,
                        "department_id": settings.department_id
                    }

            except Exception as e:
                logger.warning(f"Error fetching days data: {e}")
                # Return just the department info
                return {
                    "department": department_info,
                    "service_id": settings.service_id,
                    "department_id": settings.department_id
                }

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