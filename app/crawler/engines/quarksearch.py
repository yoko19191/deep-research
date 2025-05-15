"""
Quark Search Engine Module.

This module provides a class for performing searches on Quark and parsing the results.
It uses a browser pool to manage browser instances efficiently.
"""

from bs4 import BeautifulSoup
from app.crawler.browserpool import BrowserPool, BrowserPlaywright
from typing import Optional, List, Dict, Any
import logging
import asyncio
from app.core import load_config

# Get module logger that inherits from the root logger
logger = logging.getLogger(__name__)

# Default configuration
default_config = {
    'quark_search': {
        'base_url': 'https://ai.quark.cn/',
        'input_selector': 'textarea[placeholder="搜资料、提问题、找答案"]',
        'results_selector': 'section.sc.sc_structure_template_normal',
        'submit_selector': 'span.input-keywords-highlight',
        'wait_time': 1000,  # milliseconds
        'timeout': 5000     # milliseconds
    }
}

# Load configuration or use default
CONFIG = load_config(default_config) or default_config


class QuarkSearch:
    """
    A class for performing searches on Quark and parsing the results.
    
    This class uses a browser pool to manage browser instances and provides
    methods for executing searches and parsing the results.
    
    Attributes:
        browser_pool (BrowserPool): The pool of browser instances to use.
        base_url (str): The base URL for Quark search.
        config (dict): Configuration parameters for the search.
    """

    def __init__(self, browser_pool: BrowserPool):
        """
        Initialize a new QuarkSearch instance.
        
        Args:
            browser_pool (BrowserPool): The pool of browser instances to use.
        """
        self.browser_pool = browser_pool
        self.config = CONFIG['quark_search']
        self.base_url = self.config['base_url']
        logger.info("QuarkSearch initialized with base URL: %s", self.base_url)

    async def response(self, questions: Optional[List[str]]) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """
        Execute searches for a list of questions and return the results.
        
        Args:
            questions (Optional[List[str]]): A list of search queries.
            
        Returns:
            Optional[Dict[str, List[Dict[str, str]]]]: A dictionary mapping each question
                to a list of search results, or None if no results were found.
        """
        if not questions:
            logger.warning("No questions provided for search")
            return None
            
        results = {}
        logger.info("Processing %d search queries", len(questions))
        
        try:
            async with self.browser_pool.get_browser() as browser:
                for question in questions:
                    logger.info("Searching for: %s", question)
                    try:
                        html = await self.run(browser=browser, question=question)
                        result = self.parsing(html)
                        if result:
                            results[question] = result
                            logger.info("Found %d results for query: %s", len(result), question)
                        else:
                            logger.warning("No results found for query: %s", question)
                    except Exception as e:
                        logger.error("Error searching for '%s': %s", question, str(e))
                        # Continue with next question instead of failing completely
                        continue
        except Exception as e:
            logger.error("Failed to get browser from pool: %s", str(e))
            return None

        return results if results else None

    async def run(self, browser: BrowserPlaywright, question: Optional[str]) -> str:
        """
        Execute a search query using the provided browser instance.
        
        Args:
            browser (BrowserPlaywright): The browser instance to use.
            question (str): The search query.
            
        Returns:
            str: The HTML content of the search results page.
            
        Raises:
            TimeoutError: If the page load or search operation times out.
            Exception: For other errors during the search process.
        """
        if not question:
            logger.warning("Empty question provided for search")
            return ""
            
        logger.debug("Creating new browser context and page")
        context = await browser.browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to the search page
            logger.debug("Navigating to %s", self.base_url)
            await page.goto(self.base_url, timeout=self.config['timeout'])
            
            # Fill in the search query
            logger.debug("Entering search query: %s", question)
            await page.fill(self.config['input_selector'], question)
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Wait for and click the search button
            logger.debug("Waiting for search button")
            await page.wait_for_selector(self.config['submit_selector'], timeout=self.config['timeout'])
            await page.click(self.config['submit_selector'])
            
            # Wait for results to load
            logger.debug("Waiting for search results")
            await page.wait_for_selector(self.config['results_selector'], timeout=self.config['timeout'])
            
            # Scroll to bottom to ensure all results are loaded
            logger.debug("Scrolling to load all results")
            await page.wait_for_function('document.body !== null')
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Get the page content
            html = await page.content()
            logger.debug("Retrieved search results page content")
            return html
            
        except asyncio.TimeoutError as e:
            logger.error("Timeout while searching for '%s': %s", question, str(e))
            raise
        except Exception as e:
            logger.error("Error during search for '%s': %s", question, str(e))
            raise
        finally:
            # Always close the page and context to avoid resource leaks
            logger.debug("Closing browser page and context")
            await page.close()
            await context.close()

    def parsing(self, html: Optional[str]) -> Optional[List[Dict[str, str]]]:
        """
        Parse the HTML content of a search results page.
        
        Args:
            html (Optional[str]): The HTML content to parse.
            
        Returns:
            Optional[List[Dict[str, str]]]: A list of dictionaries containing the parsed
                search results, or None if no results were found or the HTML was invalid.
        """
        if not html:
            logger.warning("Empty HTML provided for parsing")
            return None
            
        try:
            logger.debug("Parsing search results HTML")
            soup = BeautifulSoup(html, "lxml")
            items = soup.find_all("section", class_="sc sc_structure_template_normal")
            
            if not items:
                logger.warning("No search result containers found in HTML")
                return None
                
            logger.debug("Found %d search result containers", len(items))
            results = []
            
            for item in items:
                try:
                    # Extract title
                    title_tag = item.find("div", class_="qk-title-text")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    # Extract publisher and time
                    tags = item.find_all("span", class_="qk-source-item qk-clamp-1")
                    publisher = tags[0].get_text(strip=True) if tags else ""
                    time = tags[1].get_text(strip=True) if len(tags) >= 2 else ""
                    
                    # Extract URL
                    url_tag = item.find("a", class_="qk-link-wrapper")
                    url = url_tag["href"] if url_tag and "href" in url_tag.attrs else ""
                    
                    # Extract summary
                    summary_tag = item.find("div", class_="qk-paragraph-text")
                    summary = summary_tag.get_text(strip=True) if summary_tag else ""
                    
                    data = {
                        "title": title,
                        "publisher": publisher,
                        "url": url,
                        "summary": summary,
                        "time": time
                    }
                    
                    # Only add results with a URL
                    if url:
                        results.append(data)
                    else:
                        logger.debug("Skipping result without URL: %s", title)
                except Exception as e:
                    logger.warning("Error parsing search result item: %s", str(e))
                    continue
            
            if results:
                logger.info("Parsed %d search results", len(results))
                return results
            else:
                logger.warning("No valid search results found")
                return None
                
        except Exception as e:
            logger.error("Error parsing search results HTML: %s", str(e))
            return None





