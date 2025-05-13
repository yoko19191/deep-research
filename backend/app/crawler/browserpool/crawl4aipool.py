"""
Crawler Pool Module - Manages and reuses crawl4ai crawler instances.
This module provides an efficient crawler pool implementation for managing multiple crawler instances,
enabling resource reuse and concurrency control.
"""

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode 

from contextlib import asynccontextmanager 

from asyncio import Queue, Semaphore
import asyncio 
import atexit 
import logging

# Get module logger that inherits from the root logger
logger = logging.getLogger(__name__)

# Setup class Configuration 
from core import load_config

default_config = {
        'CRAWLER': {
            'timeout': 30.0,
            'headless': True,
            'verbose': False,
            'cache_enabled': True
        }
    }


CONFIG =  load_config(default_config) or default_config


class CrawlerInstance:
    """
    Crawler Instance class - Encapsulates the creation, usage, and destruction of a single crawler instance.
    
    This class uses the async context manager pattern to ensure proper resource allocation and release.
    Each instance contains an independent browser and crawler configuration.
    """
    def __init__(self):
        """
        Initialize a crawler instance.
        
        Sets up browser configuration (headless mode, no verbose logging) and 
        crawler run configuration (cache enabled, non-streaming mode).
        """
        # 从配置文件读取参数
        self.browser_config = BrowserConfig(
            headless=CONFIG['CRAWLER']['headless'], 
            verbose=CONFIG['CRAWLER']['verbose'],
        )
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED if CONFIG['CRAWLER']['cache_enabled'] else CacheMode.DISABLED, 
            stream=False
        )
        self.crawler = None
        # 从配置文件读取超时设置
        self.default_timeout = CONFIG['CRAWLER']['timeout']
        logger.debug("CrawlerInstance initialized with timeout: %s", self.default_timeout)

    async def __aenter__(self):
        """
        Async context manager entry.
        
        Creates and initializes an AsyncWebCrawler instance.
        
        Returns:
            self: The current crawler instance.
        """
        self.crawler = AsyncWebCrawler(config=self.browser_config)
        logger.debug("AsyncWebCrawler instance created")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.
        
        Closes the crawler instance and releases associated resources.
        
        Args:
            exc_type: Exception type.
            exc_val: Exception value.
            exc_tb: Exception traceback.
        """
        if self.crawler:
            await self.crawler.close()
            logger.debug("AsyncWebCrawler instance closed")

    async def run(self, urls: list[str], timeout: float = None) -> list[dict]:
        """
        Run the crawler to fetch content from multiple URLs.
        
        Args:
            urls: List of URLs to crawl.
            timeout: Maximum time in seconds to wait for all requests to complete.
                    If None, uses the value from config.yaml.
            
        Returns:
            list[dict]: List of results containing URL and content, each result is a 
                    dictionary with url and content fields. Failed requests will include
                    an error field instead of content.
        """
        results = []
        actual_timeout = timeout if timeout is not None else self.default_timeout
        logger.info("Crawling %d URLs with timeout: %s seconds", len(urls), actual_timeout)
        
        # 如果没有提供超时参数，使用配置文件中的值
        try:
            # Set timeout for the entire batch of requests
            responses = await asyncio.wait_for(
                self.crawler.arun_many(urls=urls, config=self.run_config),
                timeout=CONFIG['CRAWLER']['timeout']
            )
            
            for r in responses:
                if r.success:
                    logger.debug("Successfully crawled URL: %s", r.url)
                    results.append({"url": r.url, "content": r.markdown})
                else:
                    # Handle failed requests with error information
                    error_msg = getattr(r, 'error', 'Unknown error')
                    logger.warning("Failed to crawl URL: %s, error: %s", r.url, error_msg)
                    results.append({"url": r.url, "error": error_msg})
                    
        except asyncio.TimeoutError:
            # Handle timeout for the entire batch
            logger.error("Timeout occurred while crawling URLs: %s", urls)
            for url in urls:
                results.append({"url": url, "error": "Request timed out"})
                
        except Exception as e:
            # Handle unexpected exceptions
            error_msg = f"Crawler error: {str(e)}"
            logger.exception("Unexpected error while crawling URLs: %s", error_msg)
            for url in urls:
                results.append({"url": url, "error": error_msg})
                
        return results

class CrawlerPool:
    """
    Crawler Pool class - Manages multiple crawler instances for resource reuse.
    
    This class implements a pool of crawler instances, using async queues and semaphores
    to control concurrency, and provides interfaces for acquiring and releasing crawler
    instances, as well as resource cleanup functionality.
    """
    def __init__(self, pool_size):
        """
        Initialize the crawler pool.
        
        Args:
            pool_size: Maximum capacity of the pool, also the maximum concurrency.
        """
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)  # Stores idle crawler instances
        self.lock = Semaphore(pool_size)      # Controls concurrency
        self.instances = []                    # Tracks all created instances
        logger.info("CrawlerPool initialized with size: %d", pool_size)
        atexit.register(lambda: asyncio.run(self.cleanup()))  # Register cleanup function on program exit

    @asynccontextmanager
    async def get_crawler(self):
        """
        Get a crawler instance as an async context manager.
        
        Uses a semaphore to control concurrency, ensuring it doesn't exceed the pool size.
        
        Usage:
            async with pool.get_crawler() as crawler:
                results = await crawler.run(urls)
        
        Yields:
            CrawlerInstance: An available crawler instance.
        """
        async with self.lock:
            logger.debug("Acquiring crawler instance from pool")
            crawler = await self._get_instance()
            try:
                yield crawler
            finally:
                await self._release_instance(crawler)
                logger.debug("Released crawler instance back to pool")

    async def _get_instance(self):
        """
        Internal method: Get a crawler instance.
        
        If there are available instances in the pool, get one from the pool;
        otherwise, create a new instance.
        
        Returns:
            CrawlerInstance: An available crawler instance.
        """
        if self.pool.empty():
            logger.debug("Creating new crawler instance (pool empty)")
            crawler = await CrawlerInstance().__aenter__()
            self.instances.append(crawler)
        else:
            logger.debug("Reusing existing crawler instance from pool")
            crawler = await self.pool.get()
        return crawler

    async def _release_instance(self, crawler: CrawlerInstance):
        """
        Internal method: Release a crawler instance.
        
        If the pool is not full, put the instance back into the pool; otherwise, discard it.
        
        Args:
            crawler: The crawler instance to release.
        """
        if self.pool.qsize() < self.pool_size:
            await self.pool.put(crawler)
        else:
            logger.debug("Pool full, discarding crawler instance")

    async def cleanup(self):
        """
        Clean up all crawler instances.
        
        Called on program exit to ensure all resources are properly released.
        """
        logger.info("Cleaning up %d crawler instances", len(self.instances))
        await asyncio.gather(*[
            crawler.__aexit__(None, None, None)
            for crawler in self.instances
        ])
        logger.info("All crawler instances cleaned up")
