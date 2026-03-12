import os
import json
import requests
import feedparser
from groq import Groq
from datetime import datetime

GROQ_API_KEY         = os.environ['GROQ_API_KEY']
BLOGGER_BLOG_ID      = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID     = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']

def get_trending_topics():
    topics = []

    # BBC News — most reliable RSS
    try:
        feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in feed.entries[:6]:
            topics.append({"title": entry.title, "source": "bbc_news"})
        print(f"BBC: {len([t for t in topics if t['source']=='bbc_news'])} topics")
    except Exception as e:
        print(f"BBC failed: {e}")

    # Reuters RSS
    try:
        feed = feedparser.parse('https://feeds.reuters.com/reuters/topNews')
        for entry in feed.entries[:5]:
            topics.append({"title": entry.title, "source": "reuters"})
        print(f"Reuters: added")
    except Exception as e:
        print(f"Reuters failed: {e}")

    # CNN RSS
    try:
        feed = feedparser.parse('http://rss.cnn.com/rss/edition.rss')
        for entry in feed.entries[:5]:
            topics.append({"title": entry.title, "source": "cnn"})
        print(f"CNN: added")
    except Exception as e:
        print(f"CNN failed: {e}")

    # Google News RSS — top stories
    try:
        feed = feedparser.parse('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en')
        for entry in feed.entries[:8]:
            topics.append({"title": entry.title, "source": "google_news"})
        print(f"Google News: added")
    except Exception as e:
        print(f"Google News failed: {e}")

    # Reddit worldnews
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; AutoBlogBot/1.0)'}
        r = requests.get('https://www.reddit.com/r/worldnews/top.json?t=day&limit=5', headers=headers, timeout=10)
        for post in r.json()['data']['children']:
            topics.append({"title": post['data']['title'], "source": "reddit_worldnews"})
        print(f"Reddit worldnews: added")
    except Exception as e:
        print(f"Reddit failed: {e}")

    # HackerNews
    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:5]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title'):
                topics.append({"title": story['title'], "source": "hackernews"})
        print(f"HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")

    print(f"\nTotal topics collected: {len(topics)}")
    return topics

def write_seo_blog_post(topics):
    client = Groq(api_key=GROQ_API_KEY)
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(topics)])
    prompt = f"""You are a world-class SEO content writer and breaking news journalist.

Today's trending topics from BBC, Reuters, CNN, Google News, Reddit:
{topics_text}

Your job: Pick the SINGLE MOST VIRAL topic from TODAY's headlines only — must be breaking news from the last 24 hours, not old stories. Ignore anything older than today.

Write a complete 1800-word SEO blog post about it.

STRICT SEO RULES:
- Title: 55-60 chars, primary keyword included naturally
- First 100 words MUST contain the primary keyword
- Use H2s that are full questions people actually Google
- Include "explained" or "what is" naturally in the post
- Add a FAQ section at the end with 5 Q&As targeting long-tail keywords
- Write like a smart human journalist — clear, helpful, zero fluff
- Strong intro hook (surprising fact or question)
- Strong conclusion

Return ONLY a valid JSON object, no markdown, no backticks:

{{
  "chosen_topic": "topic you picked",
  "title": "SEO title here",
  "meta_description": "155 char meta description with keyword",
  "primary_keyword": "main keyword",
  "secondary_keywords": ["kw1", "kw2", "kw3", "kw4"],
  "content": "FULL HTML post using <h2><p><strong><ul><li> tags only, NO html/body/head tags",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "slug": "url-friendly-slug"
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'): raw = raw[4:]
    return json.loads(raw.strip())

def build_final_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    schema = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":"{post['title']}","description":"{post['meta_description']}","datePublished":"{now_iso}","dateModified":"{now_iso}","author":{{"@type":"Organization","name":"TrendExplained"}},"publisher":{{"@type":"Organization","name":"TrendExplained"}}}}
</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{', '.join(post.get('secondary_keywords', []))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
"""
    return schema + post['content']

def get_access_token():
    r = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'refresh_token': GOOGLE_REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    }, timeout=15)
    result = r.json()
    if 'access_token' not in result:
        raise Exception(f"Token failed: {result}")
    return result['access_token']

def publish_to_blogger(post, final_content):
    token = get_access_token()
    r = requests.post(
        f'https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={'title': post['title'], 'content': final_content, 'labels': post.get('tags', [])},
        timeout=30
    )
    result = r.json()
    if 'url' in result:
        print(f"PUBLISHED: {result['url']}")
        return result['url']
    raise Exception(f"Failed: {result}")

if __name__ == '__main__':
    print(f"Starting AutoBlog — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    topics = get_trending_topics()
    post = write_seo_blog_post(topics)
    print(f"Writing about: {post['chosen_topic']}")
    final_content = build_final_content(post)
    publish_to_blogger(post, final_content)
    print("DONE!")
