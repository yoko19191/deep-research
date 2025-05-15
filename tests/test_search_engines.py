"""
Search Engine Test Module.

This module tests the functionality of various search engines by executing
search queries and verifying the results.
"""

import asyncio
import logging
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.crawler.browserpool import BrowserPool
from app.crawler.engines.baidusearch import BaiduSearch
from app.crawler.engines.bingsearch import BingSearch
from app.crawler.engines.sougousearch import SougouSearch
from app.crawler.engines.quarksearch import QuarkSearch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


def format_results_as_markdown(results: Dict[str, List[Dict[str, str]]]) -> str:
    """
    Format search results as Markdown for better readability.
    
    Args:
        results: Dictionary mapping queries to lists of search results.
        
    Returns:
        str: Markdown formatted results.
    """
    if not results:
        return "没有找到搜索结果。"
        
    markdown = ""
    
    for query, query_results in results.items():
        markdown += f"## 搜索结果: {query}\n\n"
        
        if not query_results:
            markdown += "没有找到相关结果。\n\n"
            continue
            
        for i, result in enumerate(query_results, 1):
            markdown += f"### {i}. {result.get('title', '无标题')}\n\n"
            
            if result.get('publisher'):
                markdown += f"**来源**: {result['publisher']}"
                
                if result.get('time'):
                    markdown += f" | **时间**: {result['time']}"
                    
                markdown += "\n\n"
                
            if result.get('summary'):
                markdown += f"{result['summary']}\n\n"
                
            if result.get('url'):
                markdown += f"[阅读更多]({result['url']})\n\n"
                
            markdown += "---\n\n"
            
    return markdown


async def test_search_engine(engine_name: str, engine, query: str) -> Optional[Dict[str, List[Dict[str, str]]]]:
    """
    Test a specific search engine with a query.
    
    Args:
        engine_name: Name of the search engine being tested
        engine: The search engine instance
        query: The search query to test
        
    Returns:
        Optional[Dict[str, List[Dict[str, str]]]]: The search results if successful, None otherwise.
    """
    logger.info(f"测试 {engine_name} 搜索引擎，查询: '{query}'")
    
    try:
        results = await engine.response([query])
        
        if results and query in results and results[query]:
            result_count = len(results[query])
            logger.info(f"{engine_name} 返回了 {result_count} 条结果")
            
            # 显示第一个结果的摘要
            if result_count > 0:
                first_result = results[query][0]
                logger.info(f"第一条结果: {first_result['title']}")
                logger.info(f"URL: {first_result['url']}")
                logger.info(f"摘要: {first_result['summary'][:100]}...")
            
            # 将结果保存到文件
            results_dir = Path(__file__).parent / "results"
            results_dir.mkdir(exist_ok=True)
            
            # 将结果格式化为Markdown并保存
            markdown = format_results_as_markdown(results)
            markdown_path = results_dir / f"{engine_name.lower()}_{query}.md"
            markdown_path.write_text(markdown, encoding="utf-8")
            logger.info(f"结果已保存到: {markdown_path}")
            
            # 同时保存原始JSON结果
            json_path = results_dir / f"{engine_name.lower()}_{query}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            # 打印Markdown格式的结果
            print(f"\n{'='*80}\n{engine_name} 搜索结果:\n{'='*80}\n")
            print(markdown)
            
            return results
        else:
            logger.warning(f"{engine_name} 没有返回结果")
            return None
            
    except Exception as e:
        logger.error(f"测试 {engine_name} 时出错: {str(e)}")
        return None


async def main():
    """
    Main test function that initializes and tests all search engines.
    """
    # 测试查询
    #query = "Python programming language"
    #query = "新质生产力"
    query = "产业升级"
    
    # 初始化浏览器池
    logger.info("初始化浏览器池")
    browser_pool = BrowserPool(pool_size=3)
    
    try:
        # 初始化搜索引擎
        logger.info("初始化搜索引擎")
        baidu_search = BaiduSearch(browser_pool)
        bing_search = BingSearch(browser_pool)
        sougou_search = SougouSearch(browser_pool)
        quark_search = QuarkSearch(browser_pool)
        
        # 测试每个搜索引擎
        engines = {
            "百度": baidu_search,
            "必应": bing_search,
            "搜狗": sougou_search,
            "夸克": quark_search
        }
        
        test_results = {}
        
        for name, engine in engines.items():
            logger.info(f"=== 测试 {name} 搜索引擎 ===")
            results = await test_search_engine(name, engine, query)
            test_results[name] = "成功" if results else "失败"
            logger.info(f"=== {name} 测试完成 ===\n")
        
        # 测试摘要
        logger.info("=== 测试摘要 ===")
        for name, result in test_results.items():
            logger.info(f"{name}: {result}")
            
    except Exception as e:
        logger.error(f"测试错误: {str(e)}")
    finally:
        # 清理浏览器池
        logger.info("清理浏览器池")
        await browser_pool.cleanup()


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())