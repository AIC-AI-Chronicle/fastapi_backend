import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
import aiohttp
import feedparser
import requests
from bs4 import BeautifulSoup
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import SystemMessage, HumanMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
from database import get_db_connection

class NewsAgent:
    def __init__(self, gemini_api_key: str, websocket_manager):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            google_api_key=gemini_api_key,
            temperature=0.3
        )
        self.websocket_manager = websocket_manager
        self.is_running = False
        
        # News sources
        self.news_sources = [
            "http://rss.cnn.com/rss/edition.rss",
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.reuters.com/news/news.xml",
            "https://feeds.npr.org/1001/rss.xml"
        ]

    async def send_update(self, agent_name: str, message: str, data: Optional[Dict] = None):
        """Send real-time update via WebSocket"""
        update = {
            "agent": agent_name,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        await self.websocket_manager.broadcast(json.dumps(update))

    async def fetch_news(self) -> List[Dict]:
        """Agent 1: Fetch news from multiple sources"""
        await self.send_update("News Fetcher", "Starting news fetching from multiple sources...")
        
        all_articles = []
        
        for source_url in self.news_sources:
            try:
                await self.send_update("News Fetcher", f"Fetching from {source_url}")
                
                # Parse RSS feed
                feed = feedparser.parse(source_url)
                
                for entry in feed.entries[:5]:  # Limit to 5 articles per source
                    article = {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": source_url,
                        "content": ""
                    }
                    
                    # Try to get full content
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(article["link"]) as response:
                                if response.status == 200:
                                    html = await response.text()
                                    soup = BeautifulSoup(html, 'html.parser')
                                    
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
                    
                    all_articles.append(article)
                
                await self.send_update("News Fetcher", f"Fetched {len(feed.entries[:5])} articles from {source_url}")
                
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
                
                response = await self.llm.ainvoke([HumanMessage(content=authenticity_prompt)])
                
                # Try to find similar news from other sources
                similar_articles = await self.find_similar_news(article['title'])
                
                article['authenticity_check'] = {
                    "analysis": response.content,
                    "similar_articles_count": len(similar_articles),
                    "similar_articles": similar_articles
                }
                
                verified_articles.append(article)
                
                await self.send_update("Authenticity Checker", 
                                     f"Verified: {article['title'][:50]}...", 
                                     {"similar_found": len(similar_articles)})
                
            except Exception as e:
                await self.send_update("Authenticity Checker", f"Error verifying article: {str(e)}")
        
        await self.send_update("Authenticity Checker", f"Authenticity check completed for {len(verified_articles)} articles")
        return verified_articles

    async def find_similar_news(self, title: str) -> List[str]:
        """Find similar news articles from other sources"""
        try:
            # Simple search using title keywords
            search_terms = title.split()[:3]  # Take first 3 words
            search_query = " ".join(search_terms)
            
            similar_articles = []
            
            # Search in a few news APIs (simplified version)
            # In production, you'd use proper news APIs like NewsAPI
            search_urls = [
                f"https://www.google.com/search?q={search_query}+news&tbm=nws",
            ]
            
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
                
                response = await self.llm.ainvoke([HumanMessage(content=bias_removal_prompt)])
                
                # Parse the response to extract title and content
                unbiased_content = response.content
                
                article['unbiased_version'] = unbiased_content
                unbiased_articles.append(article)
                
                await self.send_update("Bias Remover", f"Processed: {article['title'][:50]}...")
                
            except Exception as e:
                await self.send_update("Bias Remover", f"Error removing bias: {str(e)}")
        
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
                
                response = await self.llm.ainvoke([HumanMessage(content=article_generation_prompt)])
                
                # Parse the generated article
                generated_content = response.content
                
                # Create final article object
                final_article = {
                    "original_title": article['title'],
                    "original_link": article['link'],
                    "generated_content": generated_content,
                    "authenticity_score": article.get('authenticity_check', {}),
                    "processed_at": datetime.now().isoformat(),
                    "source": article['source']
                }
                
                # Save to database
                article_id = await self.save_article_to_db(final_article)
                final_article['id'] = article_id
                
                final_articles.append(final_article)
                
                await self.send_update("Article Generator", 
                                     f"Generated and saved: {article['title'][:50]}...", 
                                     {"article_id": article_id})
                
            except Exception as e:
                await self.send_update("Article Generator", f"Error generating article: {str(e)}")
        
        await self.send_update("Article Generator", f"Article generation completed. {len(final_articles)} articles saved to database")
        return final_articles

    async def save_article_to_db(self, article: Dict) -> int:
        """Save generated article to database"""
        async with get_db_connection() as conn:
            # Ensure articles table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    original_title TEXT NOT NULL,
                    original_link TEXT,
                    generated_content TEXT NOT NULL,
                    authenticity_score JSONB,
                    source TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            article_id = await conn.fetchval("""
                INSERT INTO articles (original_title, original_link, generated_content, authenticity_score, source, processed_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, 
            article['original_title'],
            article['original_link'],
            article['generated_content'],
            json.dumps(article['authenticity_score']),
            article['source'],
            datetime.fromisoformat(article['processed_at'])
            )
            
            return article_id

    async def run_pipeline(self, duration_minutes: int = 30):
        """Run the complete news processing pipeline"""
        if self.is_running:
            await self.send_update("Pipeline", "Pipeline is already running!")
            return
        
        self.is_running = True
        start_time = datetime.now()
        
        try:
            await self.send_update("Pipeline", f"Starting news processing pipeline for {duration_minutes} minutes...")
            
            while self.is_running and (datetime.now() - start_time).seconds < duration_minutes * 60:
                cycle_start = datetime.now()
                
                # Step 1: Fetch news
                articles = await self.fetch_news()
                
                if articles:
                    # Step 2: Check authenticity
                    verified_articles = await self.check_authenticity(articles)
                    
                    # Step 3: Remove bias
                    unbiased_articles = await self.remove_bias(verified_articles)
                    
                    # Step 4: Generate and save articles
                    final_articles = await self.generate_articles(unbiased_articles)
                    
                    cycle_time = (datetime.now() - cycle_start).seconds
                    await self.send_update("Pipeline", 
                                         f"Cycle completed in {cycle_time}s. Processed {len(final_articles)} articles")
                
                # Wait before next cycle (5 minutes)
                await asyncio.sleep(300)
            
            await self.send_update("Pipeline", "News processing pipeline completed successfully!")
            
        except Exception as e:
            await self.send_update("Pipeline", f"Pipeline error: {str(e)}")
        finally:
            self.is_running = False

    def stop_pipeline(self):
        """Stop the running pipeline"""
        self.is_running = False