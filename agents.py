import asyncio
import json
import uuid
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import aiohttp
import feedparser
import requests
from bs4 import BeautifulSoup
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import os
from database import (
    get_db_connection, log_agent_activity, create_pipeline_run, 
    update_pipeline_status, update_pipeline_progress, save_article_to_db,
    update_article_blockchain_info
)
from blockchain_integration import integrate_blockchain_hashing

class NewsAgent:
    def __init__(self, gemini_api_key: str, websocket_manager):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=gemini_api_key,
            temperature=0.3
        )
        self.websocket_manager = websocket_manager
        self.is_running = False
        self.current_pipeline_id = None
        self.start_time = None
        self.current_cycle = 0
        self.total_articles_processed = 0
        
        # News sources
        self.news_sources = [
            "http://rss.cnn.com/rss/edition.rss",
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.reuters.com/news/news.xml",
            "https://feeds.npr.org/1001/rss.xml"
        ]

    async def send_update(self, agent_name: str, message: str, data: Optional[Dict] = None):
        """Send real-time update via WebSocket and log to database"""
        update = {
            "agent": agent_name,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "pipeline_id": self.current_pipeline_id,
            "cycle": self.current_cycle,
            "data": data or {}
        }
        
        # Send WebSocket update
        try:
            await self.websocket_manager.broadcast(json.dumps(update))
        except Exception as e:
            print(f"WebSocket broadcast error: {e}")
        
        # Log to database with proper data handling
        if self.current_pipeline_id:
            try:
                # Only pass the data part, not the entire update object
                await log_agent_activity(
                    self.current_pipeline_id, 
                    agent_name, 
                    message, 
                    "INFO", 
                    data  # Pass only the data dict, not the entire update
                )
            except Exception as e:
                print(f"Database logging error: {e}")

    async def fetch_news(self) -> List[Dict]:
        """Agent 1: Fetch news from multiple sources"""
        await self.send_update("News Fetcher", "Starting news fetching from multiple sources...")
        
        all_articles = []
        
        for source_url in self.news_sources:
            try:
                await self.send_update("News Fetcher", f"Fetching from {source_url}")
                
                # Parse RSS feed
                feed = feedparser.parse(source_url)
                
                for entry in feed.entries[:3]:  # Limit to 3 articles per source for demo
                    # Extract image URL from RSS entry
                    image_url = None
                    
                    # Try different ways to get image URL from RSS
                    if hasattr(entry, 'media_content') and entry.media_content:
                        image_url = entry.media_content[0].get('url')
                    elif hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                        image_url = entry.media_thumbnail[0].get('url')
                    elif hasattr(entry, 'enclosures') and entry.enclosures:
                        for enclosure in entry.enclosures:
                            if enclosure.type and 'image' in enclosure.type:
                                image_url = enclosure.href
                                break
                    
                    article = {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "image_url": image_url,
                        "published": entry.get("published", ""),
                        "source": source_url,
                        "content": ""
                    }
                    
                    # Try to get full content and extract image if not found in RSS
                    try:
                        timeout = aiohttp.ClientTimeout(total=10)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(article["link"]) as response:
                                if response.status == 200:
                                    html = await response.text()
                                    soup = BeautifulSoup(html, 'html.parser')
                                    
                                    # Extract image URL if not found in RSS
                                    if not image_url:
                                        # Try to find Open Graph image
                                        og_image = soup.find('meta', property='og:image')
                                        if og_image and og_image.get('content'):
                                            article["image_url"] = og_image.get('content')
                                        else:
                                            # Try to find Twitter card image
                                            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                                            if twitter_image and twitter_image.get('content'):
                                                article["image_url"] = twitter_image.get('content')
                                            else:
                                                # Try to find first img tag in content
                                                first_img = soup.find('img')
                                                if first_img and first_img.get('src'):
                                                    src = first_img.get('src')
                                                    # Make sure it's a full URL
                                                    if src.startswith('//'):
                                                        article["image_url"] = 'https:' + src
                                                    elif src.startswith('/'):
                                                        from urllib.parse import urljoin
                                                        article["image_url"] = urljoin(article["link"], src)
                                                    elif src.startswith('http'):
                                                        article["image_url"] = src
                                    
                                    # Remove script and style elements
                                    for script in soup(["script", "style"]):
                                        script.decompose()
                                    
                                    # Get text content
                                    text = soup.get_text()
                                    lines = (line.strip() for line in text.splitlines())
                                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                                    article["content"] = ' '.join(chunk for chunk in chunks if chunk)[:2000]
                    except Exception as e:
                        await self.send_update("News Fetcher", f"Error fetching content for {article['title']}: {str(e)}")
                        article["content"] = article["summary"]  # Fallback to summary
                    
                    all_articles.append(article)
                
                await self.send_update("News Fetcher", f"Fetched {len(feed.entries[:3])} articles from {source_url}")
                
            except Exception as e:
                await self.send_update("News Fetcher", f"Error fetching from {source_url}: {str(e)}")
        
        await self.send_update("News Fetcher", f"Total articles fetched: {len(all_articles)}", {"count": len(all_articles)})
        return all_articles

    async def check_authenticity(self, articles: List[Dict]) -> List[Dict]:
        """Agent 2: Check authenticity and find similar news"""
        await self.send_update("Authenticity Checker", "Starting authenticity verification...")
        
        verified_articles = []
        
        for i, article in enumerate(articles):
            try:
                await self.send_update("Authenticity Checker", f"Verifying article {i+1}/{len(articles)}: {article['title'][:50]}...")
                
                # Use Gemini to analyze the content for authenticity
                authenticity_prompt = f"""
                Analyze the following news article for authenticity and credibility:
                
                Title: {article['title']}
                Content: {article['content'][:1000]}
                Source: {article['source']}
                
                Provide a credibility score from 1-10 and explain your reasoning.
                Also identify if this appears to be legitimate news or potentially fake/misleading.
                
                Response format:
                Credibility Score: X/10
                Reasoning: [Your analysis]
                Legitimate: Yes/No
                """
                
                try:
                    response = await self.llm.ainvoke([HumanMessage(content=authenticity_prompt)])
                    
                    # Try to find similar news from other sources
                    similar_articles = await self.find_similar_news(article['title'])
                    
                    article['authenticity_check'] = {
                        "analysis": response.content,
                        "similar_articles_count": len(similar_articles),
                        "similar_articles": similar_articles,
                        "verified_at": datetime.now().isoformat()
                    }
                    
                except Exception as llm_error:
                    await self.send_update("Authenticity Checker", f"LLM error for article: {str(llm_error)}")
                    article['authenticity_check'] = {
                        "analysis": "Error during analysis",
                        "similar_articles_count": 0,
                        "similar_articles": [],
                        "error": str(llm_error)
                    }
                
                verified_articles.append(article)
                
                await self.send_update("Authenticity Checker", 
                                     f"Verified: {article['title'][:50]}...", 
                                     {"similar_found": len(article['authenticity_check']['similar_articles'])})
                
            except Exception as e:
                await self.send_update("Authenticity Checker", f"Error verifying article: {str(e)}")
                article['authenticity_check'] = {"error": str(e)}
                verified_articles.append(article)
        
        await self.send_update("Authenticity Checker", f"Authenticity check completed for {len(verified_articles)} articles")
        return verified_articles

    async def find_similar_news(self, title: str) -> List[str]:
        """Find similar news articles from other sources"""
        try:
            # Simple search using title keywords
            search_terms = title.split()[:3]  # Take first 3 words
            search_query = " ".join(search_terms)
            
            # For demo, return mock similar articles
            similar_articles = [
                f"Similar article 1 for: {title[:30]}...",
                f"Similar article 2 for: {title[:30]}..."
            ]
            
            return similar_articles
            
        except Exception as e:
            return []

    async def remove_bias(self, articles: List[Dict]) -> List[Dict]:
        """Agent 3: Remove bias from news articles"""
        await self.send_update("Bias Remover", "Starting bias removal process...")
        
        unbiased_articles = []
        
        for i, article in enumerate(articles):
            try:
                await self.send_update("Bias Remover", f"Processing article {i+1}/{len(articles)}: {article['title'][:50]}...")
                
                bias_removal_prompt = f"""
                Remove bias from the following news article while maintaining factual accuracy:
                
                Original Title: {article['title']}
                Original Content: {article['content']}
                
                Please rewrite this article to:
                1. Remove emotional language and subjective opinions
                2. Present facts objectively
                3. Remove any political or ideological bias
                4. Maintain the core information and facts
                5. Use neutral, professional language
                
                Return only the unbiased version without explanations.
                
                Format:
                Title: [Unbiased title]
                Content: [Unbiased content]
                """
                
                try:
                    response = await self.llm.ainvoke([HumanMessage(content=bias_removal_prompt)])
                    article['unbiased_version'] = response.content
                except Exception as llm_error:
                    await self.send_update("Bias Remover", f"LLM error: {str(llm_error)}")
                    article['unbiased_version'] = article['content']  # Fallback to original
                
                unbiased_articles.append(article)
                
                await self.send_update("Bias Remover", f"Processed: {article['title'][:50]}...")
                
            except Exception as e:
                await self.send_update("Bias Remover", f"Error removing bias: {str(e)}")
                article['unbiased_version'] = article['content']  # Fallback to original
                unbiased_articles.append(article)
        
        await self.send_update("Bias Remover", f"Bias removal completed for {len(unbiased_articles)} articles")
        return unbiased_articles

    async def generate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Agent 4: Generate final articles and save to database"""
        await self.send_update("Article Generator", "Starting article generation...")
        
        final_articles = []
        
        for i, article in enumerate(articles):
            try:
                await self.send_update("Article Generator", f"Generating final article {i+1}/{len(articles)}: {article['title'][:50]}...")
                
                article_generation_prompt = f"""
                Create a comprehensive, well-structured news article based on the following information:
                
                Original Title: {article['title']}
                Unbiased Content: {article.get('unbiased_version', article['content'])}
                Authenticity Info: {article.get('authenticity_check', {}).get('analysis', 'Not available')}
                
                Create a professional news article with:
                1. A compelling but factual headline
                2. A clear lead paragraph summarizing the key facts
                3. Well-organized body paragraphs
                4. Proper journalistic structure
                5. Objective, factual tone
                
                Format the response as:
                HEADLINE: [Your headline]
                LEAD: [Lead paragraph]
                BODY: [Main article body]
                TAGS: [Relevant tags separated by commas]
                """
                
                try:
                    response = await self.llm.ainvoke([HumanMessage(content=article_generation_prompt)])
                    generated_content = response.content
                except Exception as llm_error:
                    await self.send_update("Article Generator", f"LLM error: {str(llm_error)}")
                    generated_content = f"HEADLINE: {article['title']}\nLEAD: {article['content'][:200]}...\nBODY: Content generation failed\nTAGS: news, error"
                
                # Save to database using the database function (now includes image_url)
                article_id = await save_article_to_db(
                    pipeline_id=self.current_pipeline_id,
                    original_title=article['title'],
                    original_link=article['link'],
                    image_url=article.get('image_url'),
                    generated_content=generated_content,
                    authenticity_score=article.get('authenticity_check', {}),
                    source=article['source'],
                    cycle_number=self.current_cycle
                )
                
                # Create final article object
                final_article = {
                    "id": article_id,
                    "original_title": article['title'],
                    "original_link": article['link'],
                    "image_url": article.get('image_url'),
                    "generated_content": generated_content,
                    "authenticity_score": article.get('authenticity_check', {}),
                    "processed_at": datetime.now().isoformat(),
                    "source": article['source'],
                    "pipeline_id": self.current_pipeline_id,
                    "cycle_number": self.current_cycle
                }
                
                final_articles.append(final_article)
                self.total_articles_processed += 1
                
                await self.send_update("Article Generator", 
                                     f"Generated and saved: {article['title'][:50]}...", 
                                     {"article_id": article_id, "has_image": bool(article.get('image_url'))})
                
            except Exception as e:
                await self.send_update("Article Generator", f"Error generating article: {str(e)}")
        
        await self.send_update("Article Generator", f"Article generation completed. {len(final_articles)} articles saved to database")
        return final_articles

    async def run_pipeline(self, duration_minutes: int = 30):
        """Run the complete news processing pipeline"""
        if self.is_running:
            await self.send_update("Pipeline", "Pipeline is already running", {"error": True})
            return
        
        self.is_running = True
        self.current_pipeline_id = str(uuid.uuid4())
        self.start_time = datetime.now()
        self.current_cycle = 0
        self.total_articles_processed = 0

        try:
            await self.send_update("Pipeline", f"Pipeline started for {duration_minutes} minutes", {"duration_minutes": duration_minutes})
            
            # Create pipeline run record
            await create_pipeline_run(self.current_pipeline_id, duration_minutes)
            
            end_time = self.start_time + timedelta(minutes=duration_minutes)
            
            while self.is_running and datetime.now() < end_time:
                self.current_cycle += 1
                cycle_start = datetime.now()
                
                await self.send_update("Pipeline", f"Starting cycle {self.current_cycle}...", {
                    "cycle": self.current_cycle,
                    "time_remaining": str(end_time - datetime.now())
                })
                
                # Step 1: Fetch news
                articles = await self.fetch_news()
                
                if articles:
                    # Step 2: Check authenticity
                    verified_articles = await self.check_authenticity(articles)
                    
                    # Step 3: Remove bias
                    unbiased_articles = await self.remove_bias(verified_articles)
                    
                    # Step 4: Generate and save articles
                    final_articles = await self.generate_articles(unbiased_articles)
                    
                    # Step 5: Store articles on blockchain and update database
                    await self.send_update("Pipeline", "Starting blockchain storage process...")
                    blockchain_articles = await integrate_blockchain_hashing(
                        final_articles, 
                        self.current_pipeline_id, 
                        self.websocket_manager
                    )
                    
                    # Update each article in database with blockchain information
                    blockchain_stored_count = 0
                    for article in blockchain_articles:
                        if article.get('blockchain_hashes') or article.get('blockchain_stored'):
                            try:
                                blockchain_info = {
                                    'stored_on_chain': article.get('blockchain_stored', False),
                                    'transaction_hash': article.get('blockchain_transaction', {}).get('transaction_hash'),
                                    'blockchain_article_id': article.get('blockchain_transaction', {}).get('article_id'),
                                    'network': article.get('blockchain_network', 'bsc_testnet'),
                                    'explorer_url': article.get('blockchain_transaction', {}).get('explorer_url'),
                                    'content_hash': article.get('blockchain_hashes', {}).get('content_hash'),
                                    'metadata_hash': article.get('blockchain_hashes', {}).get('metadata_hash')
                                }
                                
                                # Update article in database with blockchain info
                                await update_article_blockchain_info(article.get('id'), blockchain_info)
                                
                                if blockchain_info.get('stored_on_chain'):
                                    blockchain_stored_count += 1
                                    
                                    # Log successful blockchain storage
                                    await log_agent_activity(
                                        self.current_pipeline_id,
                                        "Blockchain Storage",
                                        f"Article {article.get('id')} stored on blockchain with TX: {blockchain_info.get('transaction_hash', '')[:10]}...",
                                        "INFO",
                                        {
                                            "article_id": article.get('id'),
                                            "blockchain_article_id": blockchain_info.get('blockchain_article_id'),
                                            "transaction_hash": blockchain_info.get('transaction_hash'),
                                            "explorer_url": blockchain_info.get('explorer_url'),
                                            "network": blockchain_info.get('network')
                                        }
                                    )
                                
                            except Exception as e:
                                await log_agent_activity(
                                    self.current_pipeline_id,
                                    "Blockchain Storage",
                                    f"Error updating article {article.get('id')} with blockchain info: {str(e)}",
                                    "ERROR"
                                )
                    
                    # Update progress
                    try:
                        await update_pipeline_progress(self.current_pipeline_id, self.current_cycle, self.total_articles_processed)
                    except Exception as e:
                        await self.send_update("Pipeline", f"Error updating progress: {str(e)}")
                    
                    cycle_time = (datetime.now() - cycle_start).seconds
                    
                    await self.send_update("Pipeline", 
                                         f"Cycle {self.current_cycle} completed in {cycle_time}s. Processed {len(final_articles)} articles, {blockchain_stored_count} stored on blockchain", {
                                             "cycle": self.current_cycle,
                                             "articles_in_cycle": len(final_articles),
                                             "blockchain_stored": blockchain_stored_count,
                                             "total_articles": self.total_articles_processed,
                                             "cycle_duration": cycle_time
                                         })
                else:
                    await self.send_update("Pipeline", f"No articles fetched in cycle {self.current_cycle}")
                
                # Wait before next cycle (5 minutes) or check if time is up
                remaining_time = (end_time - datetime.now()).total_seconds()
                if remaining_time > 300:  # More than 5 minutes left
                    await asyncio.sleep(300)  # Wait 5 minutes
                elif remaining_time > 0:
                    await asyncio.sleep(remaining_time)  # Wait remaining time
                else:
                    break  # Time is up
            
            # Pipeline completed
            await update_pipeline_status(self.current_pipeline_id, "COMPLETED")
            await self.send_update("Pipeline", f"News processing pipeline completed successfully! Processed {self.total_articles_processed} articles in {self.current_cycle} cycles.", {
                "status": "COMPLETED",
                "total_articles": self.total_articles_processed,
                "total_cycles": self.current_cycle,
                "duration": str(datetime.now() - self.start_time)
            })
            
        except Exception as e:
            await update_pipeline_status(self.current_pipeline_id, "ERROR", str(e))
            await self.send_update("Pipeline", f"Pipeline error: {str(e)}", {"status": "ERROR", "error": str(e)})
            await log_agent_activity(
                self.current_pipeline_id,
                "Pipeline",
                f"Pipeline error: {str(e)}",
                "ERROR"
            )
        finally:
            await self.send_update("Pipeline", "Pipeline stopped")
            self.is_running = False
            self.current_pipeline_id = None

    def stop_pipeline(self):
        """Stop the running pipeline"""
        if self.is_running and self.current_pipeline_id:
            self.is_running = False
            # Update database status will be handled by the main loop
            asyncio.create_task(self._stop_pipeline_cleanup())

    async def _stop_pipeline_cleanup(self):
        """Cleanup after stopping pipeline"""
        if self.current_pipeline_id:
            await update_pipeline_status(self.current_pipeline_id, "STOPPED")
            await self.send_update("Pipeline", "Pipeline stopped by user", {"status": "STOPPED"})

    def get_status(self):
        """Get current pipeline status"""
        return {
            "is_running": self.is_running,
            "pipeline_id": self.current_pipeline_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "current_cycle": self.current_cycle,
            "total_articles_processed": self.total_articles_processed
        }