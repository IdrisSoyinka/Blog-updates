import os
import logging
import requests
from bs4 import BeautifulSoup
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import re
import feedparser
import time
from datetime import datetime, timedelta, timezone
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s',
    handlers=[
        logging.FileHandler("blog_automation.log"),
        logging.StreamHandler()
    ]
)

# Load environment variables
env_path = Path(__file__).parent / '.env'

if not env_path.is_file():
    logging.error(f".env file not found at {env_path}")
    exit(1)

load_success = load_dotenv(dotenv_path=env_path)

if not load_success:
    logging.error(f"Failed to load .env file from {env_path}")
    exit(1)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BLOGGER_CLIENT_SECRET_FILE = os.getenv("BLOGGER_CLIENT_SECRET_FILE")
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Define RSS feeds
RSS_FEEDS = [
    "https://www.nature.com/nbt/rss/current.xml",  # Nature Biotechnology instead of nature.com/nature/articles
    "https://www.sciencemag.org/rss/news_current.xml",
    
]

def fetch_rss_feeds(rss_urls):
    articles = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            fetched = len(feed.entries)
            articles.extend(feed.entries)
            logging.info(f"Fetched {fetched} articles from {url}")
        except Exception as e:
            logging.error(f"Error fetching RSS feed {url}: {e}")
    return articles

def deduplicate_articles(articles):
    seen = set()
    unique = []
    for article in articles:
        if 'link' in article and article['link'] not in seen:
            unique.append(article)
            seen.add(article['link'])
    logging.info(f"Unique articles after deduplication: {len(unique)}")
    return unique

def filter_recent_articles(articles, days=1):
    recent = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for article in articles:
        pub_date = None

        if 'published_parsed' in article and article.published_parsed:
            pub_date = datetime(*article.published_parsed[:6], tzinfo=timezone.utc)
        elif 'updated_parsed' in article and article.updated_parsed:
            pub_date = datetime(*article.updated_parsed[:6], tzinfo=timezone.utc)
        elif 'published' in article and article.published:
            try:
                pub_date = datetime.fromtimestamp(time.mktime(time.strptime(article.published, '%a, %d %b %Y %H:%M:%S %Z')), tz=timezone.utc)
            except Exception as e:
                logging.error(f"Error parsing 'published' date for article '{article['title']}': {e}")
        elif 'updated' in article and article.updated:
            try:
                pub_date = datetime.fromtimestamp(time.mktime(time.strptime(article.updated, '%a, %d %b %Y %H:%M:%S %Z')), tz=timezone.utc)
            except Exception as e:
                logging.error(f"Error parsing 'updated' date for article '{article['title']}': {e}")
        else:
            logging.warning(f"No publication date found for article: {article['title']}. Assigning current UTC time.")
            pub_date = datetime.now(timezone.utc)

        if pub_date and pub_date >= cutoff:
            recent.append(article)

    logging.info(f"Articles published within the last {days} day(s): {len(recent)}")
    return recent

def extract_reference_links(article_url, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    for attempt in range(retries):
        try:
            response = requests.get(article_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            links = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith('http'):
                    links.add(href)
            return list(links)[:5]  # Limit to top 5 references
        except requests.exceptions.RequestException as err:
            logging.error(f"Error occurred: {err} for URL {article_url}")
        
        wait_time = 2 ** attempt
        logging.info(f"Retrying in {wait_time} seconds...")
        time.sleep(wait_time)

    logging.error(f"Failed to extract links from {article_url} after {retries} attempts.")
    return []

def markdown_to_html(markdown_text):
    # A simple Markdown to HTML converter
    html = markdown_text.replace('\n\n', '<br><br>')
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)
    return html

def clean_generated_content(content):
    unwanted_terms = ["delve", "in conclusion", "underscores", "ground breaking"]
    for term in unwanted_terms:
        content = re.sub(r'\b' + re.escape(term) + r'\b', '', content, flags=re.IGNORECASE)
    return content

def generate_blog_content(article, model="gpt-4o-mini", max_tokens=1500, temperature=0.7):
    reference_links = extract_reference_links(article['link'])
    references = "\n".join([f"- [{i+1}]({link})" for i, link in enumerate(reference_links)])
    
    summary_text = BeautifulSoup(article.get('summary', 'No Summary'), 'html.parser').get_text()
    
    system_prompt = "You are a tech-savvy journalist writing an article for TechCrunch."

    user_prompt = f"""
Title: {article.get('title', 'No Title')}
Link: {article.get('link', 'No Link')}
Summary: {summary_text}

Requirements:
- Write in the clear, concise, and informative style typical of TechCrunch.
- Use proper paragraph structuring for readability.
- Use at least two paragraphs, each focusing on a distinct aspect of the topic.

Generate the article below:
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        
        if finish_reason != "stop":
            logging.warning(f"Content generation didn't complete normally. Reason: {finish_reason}")
            if finish_reason == "length":
                content += "\n\n[Note: The response was truncated due to length limitations.]"

        # Clean unwanted terms
        content = clean_generated_content(content)

        if reference_links:
            content += "\n\n**References:**\n" + references

        # Convert Markdown to HTML
        content = markdown_to_html(content)

        # Log token usage
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens
        logging.info(f"Token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

        return content
    except Exception as e:
        logging.error(f"Error generating content for article '{article.get('title', 'No Title')}': {str(e)}")
        return None

def format_blog_post(title, content):
    return {
        "title": title,
        "content": content
    }

def get_blogger_service():
    SCOPES = ['https://www.googleapis.com/auth/blogger']
    try:
        if not BLOGGER_CLIENT_SECRET_FILE:
            raise ValueError("BLOGGER_CLIENT_SECRET_FILE is not set in the environment variables.")

        if not os.path.exists(BLOGGER_CLIENT_SECRET_FILE):
            raise FileNotFoundError(f"credentials.json not found at {BLOGGER_CLIENT_SECRET_FILE}")

        logging.info(f"Loading credentials from: {BLOGGER_CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(
            BLOGGER_CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        service = build('blogger', 'v3', credentials=creds)
        logging.info("Authenticated with Google Blogger API successfully.")
        return service
    except Exception as e:
        logging.error(f"Error authenticating with Google Blogger API: {e}")
        return None

def publish_blog_post(post, service, retries=3):
    for attempt in range(retries):
        try:
            if not BLOGGER_BLOG_ID:
                logging.error("BLOGGER_BLOG_ID is not set.")
                return

            published_post = service.posts().insert(blogId=str(BLOGGER_BLOG_ID), body=post).execute()
            logging.info(f"Post published successfully: {published_post.get('url')}")
            return
        except HttpError as e:
            if e.resp.status in [429, 500, 502, 503, 504]:
                wait = (2 ** attempt) + random.random()
                logging.warning(f"HTTP Error {e.resp.status}: {e.content}. Retrying in {wait:.2f} seconds...")
                time.sleep(wait)
            else:
                error_content = e.content.decode('utf-8') if hasattr(e, 'content') else str(e)
                logging.error(f"HTTP Error {e.resp.status}: {error_content}")
                break
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            break
    logging.error(f"Failed to publish post '{post['title']}' after {retries} attempts.")

def load_published_links(blog_id):
    file_path = f"published_links_{blog_id}.txt"
    if not os.path.exists(file_path):
        return set()
    with open(file_path, 'r') as f:
        return set(line.strip() for line in f)

def save_published_links(blog_id, links):
    file_path = f"published_links_{blog_id}.txt"
    with open(file_path, 'a') as f:
        for link in links:
            f.write(f"{link}\n")

def get_latest_articles():
    all_articles = fetch_rss_feeds(RSS_FEEDS)
    unique_articles = deduplicate_articles(all_articles)
    recent_articles = filter_recent_articles(unique_articles, days=1)
    # Limit to the latest 10 articles
    return recent_articles[:10]

def main():
    articles = get_latest_articles()

    if not articles:
        logging.info("No articles found to process. Exiting.")
        return

    published_links = load_published_links(BLOGGER_BLOG_ID)

    service = get_blogger_service()
    if not service:
        logging.error("Google Blogger service not available. Exiting.")
        return

    new_published_links = []
    for article in articles:
        if article.get('link') in published_links:
            logging.info(f"Article already published: {article.get('title', 'No Title')}")
            continue

        logging.info(f"Processing article: {article.get('title', 'No Title')}")
        content = generate_blog_content(article)
        if content:
            post_title = f"{article.get('title', 'No Title')} - Insights on Science, Law, and Technology Transfer"
            post = format_blog_post(post_title, content)
            publish_blog_post(post, service)
            new_published_links.append(article.get('link'))
        else:
            logging.warning(f"Skipping article '{article.get('title', 'No Title')}' due to content generation failure.")

    save_published_links(BLOGGER_BLOG_ID, new_published_links)

    logging.info("All articles processed.")

if __name__ == "__main__":
    main()
