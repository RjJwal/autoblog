import os
import json
import requests
import feedparser
import google.generativeai as genai
from datetime import datetime

GEMINI_API_KEY       = os.environ['GEMINI_API_KEY']
BLOGGER_BLOG_ID      = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID     = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']

def get_trending_topics():
    topics = []
    try:
        feed = feedparser.parse('https://trends.google.com/trends/trendingsearches/daily/rss?geo=US')
        for entry in feed.entries[:8]:
            topics.append({"title": entry.title, "source": "google_trends"})
    except: pass
    try:
        headers = {'User-Agent': 'AutoBlogBot/1.0'}
        r = requests.get('https://www.reddit.com/r/worldnews/top.json?t=day&limit=5', headers=headers, timeout=10)
        for post in r.json()['data']['children']:
            topics.append({"title": post['data']['title'], "source": "reddit"})
    except: pass
    try:
        headers = {'User-Agent': 'AutoBlogBot/1.0'}
        r = requests.get('https://www.reddit.com/r/technology/top.json?t=day&limit=5', headers=headers, timeout=10)
        for post in r.json()['data']['children']:
            topics.append({"title": post['data']['title'], "source": "reddit_tech"})
    except: pass
    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:5]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title'):
                topics.append({"title": story['title'], "source": "hackernews"})
    except: pass
    print(f"Total topics: {len(topics)}")
    return topics

def write_seo_blog_post(topics):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(topics)])
    prompt = f"""You are a world-class SEO content writer and journalist.

Today's trending topics:
{topics_text}

Pick the SINGLE BEST topic for maximum Google search traffic and write a complete 1800-word SEO blog post.

STRICT SEO RULES:
- Title: 55-60 chars, primary keyword included naturally
- First 100 words MUST contain the primary keyword
- Use H2s that are full questions people Google
- Include exact phrase "explained" or "what is" naturally in the post
- Add a FAQ section at the end with 5 Q&As targeting long-tail keywords
- Write like a smart human journalist — clear, helpful, zero fluff
- Add transition sentences between every section
- Include a strong intro hook (surprising fact or question)
- End with a strong conclusion

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

    response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.7))
    raw = response.text.strip()
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
