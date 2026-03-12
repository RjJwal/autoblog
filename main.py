import os
import json
import time
import requests
import feedparser
from groq import Groq
from datetime import datetime

GROQ_API_KEY         = os.environ['GROQ_API_KEY']
BLOGGER_BLOG_ID      = os.environ['BLOGGER_BLOG_ID']
GOOGLE_REFRESH_TOKEN = os.environ['GOOGLE_REFRESH_TOKEN']
GOOGLE_CLIENT_ID     = os.environ['GOOGLE_CLIENT_ID']
GOOGLE_CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']

BLOCKLIST = [
    'trump indictment', 'pleads not guilty', '34 felony',
    'hush money', 'stormy daniels', 'temporal javascript',
    '9-year journey', 'knitting', 'common lisp', 'rails 2026'
]

def is_blocked(title):
    t = title.lower()
    return any(b in t for b in BLOCKLIST)

def get_trending_topics():
    topics = []

    try:
        feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in feed.entries[:6]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "bbc_news"})
        print(f"BBC: added")
    except Exception as e:
        print(f"BBC failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.reuters.com/reuters/topNews')
        for entry in feed.entries[:6]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "reuters"})
        print(f"Reuters: added")
    except Exception as e:
        print(f"Reuters failed: {e}")

    try:
        feed = feedparser.parse('https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en')
        for entry in feed.entries[:12]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "google_news"})
        print(f"Google News: added")
    except Exception as e:
        print(f"Google News failed: {e}")

    try:
        feed = feedparser.parse('https://feeds.skynews.com/feeds/rss/world.xml')
        for entry in feed.entries[:5]:
            if not is_blocked(entry.title):
                topics.append({"title": entry.title, "source": "sky_news"})
        print(f"Sky News: added")
    except Exception as e:
        print(f"Sky News failed: {e}")

    try:
        r = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        for sid in r.json()[:5]:
            story = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5).json()
            if story.get('title') and not is_blocked(story['title']):
                topics.append({"title": story['title'], "source": "hackernews"})
        print(f"HackerNews: added")
    except Exception as e:
        print(f"HackerNews failed: {e}")

    print(f"\n=== FETCHED HEADLINES ===")
    for i, t in enumerate(topics):
        print(f"{i+1}. [{t['source']}] {t['title']}")
    print(f"=== TOTAL: {len(topics)} ===\n")
    return topics

def write_seo_blog_post(topics, used_topics=[]):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.utcnow().strftime('%B %d, %Y')

    remaining = [t for t in topics if t['title'] not in used_topics]
    google_topics = [t for t in remaining if t['source'] == 'google_news']
    other_topics  = [t for t in remaining if t['source'] != 'google_news']
    ordered = google_topics + other_topics
    topics_text = '\n'.join([f"{i+1}. [{t['source']}] {t['title']}" for i, t in enumerate(ordered)])

    # Step 1: Pick best topic
    pick_prompt = f"""Today is {today}.

Real headlines fetched RIGHT NOW:
{topics_text}

Pick the single headline that most people would be Googling RIGHT NOW today.
Prefer [google_news] and [bbc_news] sources. Ignore developer/niche tech topics.
Reply with ONLY the exact headline text from the list. Nothing else."""

    pick_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": pick_prompt}],
        temperature=0.1
    )
    chosen = pick_response.choices[0].message.content.strip()
    print(f"AI chose: {chosen}")

    # Step 2: Write world-class SEO post
    write_prompt = f"""You are a Pulitzer-level journalist and world-class SEO expert. Today is {today}.

Write a MASTERPIECE 2000-word SEO blog post about this breaking news story:
"{chosen}"

=== 2026 SEO RULES (follow ALL of these) ===

TITLE (critical):
- 55-60 characters exactly
- Include primary long-tail keyword naturally
- Use power words: "Explained", "What You Need to Know", "Breaking", "Here's Why", "Everything You Need to Know"
- Make it irresistible to click

INTRO HOOK (first 150 words — most important):
- Open with ONE shocking fact, surprising statistic, or bold controversial statement
- Do NOT start with "In a world..." or "Did you know..."
- Use second person ("You") to pull reader in immediately
- Primary keyword must appear within first 100 words naturally
- End intro with a preview of what they'll learn — create curiosity gap

CONTENT STRUCTURE:
- H2 headings must be FULL QUESTIONS people type into Google (e.g. "What Does This Mean for Oil Prices in 2026?")
- Each section: 200-250 words, one clear idea, ends with transition to next section
- Use <strong> to bold key facts and statistics
- Add at least one <ul> list per post with 4-6 bullet points
- Include real-world implications and human impact angle
- Explain complex things in simple language (write for a smart 16-year-old)
- Add a "What Experts Are Saying" section with attributed quotes (you can create realistic expert quotes)
- Add a "What Happens Next" section near the end — people always search this

LONG-TAIL KEYWORD STRATEGY:
- Primary keyword: 1-2 words, used 8-12 times naturally
- 4 secondary long-tail keywords: 3-5 words each, used 2-3 times each
- Include natural variations and synonyms (semantic SEO)
- Never stuff keywords — must read naturally

FAQ SECTION (critical for Google featured snippets):
- 6 Q&As minimum
- Questions must be EXACTLY what people type into Google
- Answers: 40-60 words each — concise, direct, complete
- Include "when", "why", "how", "what", "who" questions

EEAT SIGNALS (Google trusts sites that show these):
- Mention specific dates, numbers, and statistics
- Reference real organizations, governments, experts by name
- Show cause-and-effect reasoning
- Add context that shows deep understanding of the topic

SCHEMA & TECHNICAL:
- Use only <h2><p><strong><ul><li> HTML tags
- NO html/body/head tags

Return ONLY a valid JSON object. No markdown. No backticks. No extra text outside the JSON:

{{
  "chosen_topic": "exact headline",
  "title": "Perfect 55-60 char SEO title with power word",
  "meta_description": "Compelling 150-155 char description with primary keyword and clear value proposition",
  "primary_keyword": "main 1-2 word keyword",
  "secondary_keywords": ["long tail keyword 1", "long tail keyword 2", "long tail keyword 3", "long tail keyword 4"],
  "content": "FULL 2000-word HTML post",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "slug": "url-friendly-slug-with-keyword"
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": write_prompt}],
        temperature=0.7,
        max_tokens=4000
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'): raw = raw[4:]
    result = json.loads(raw.strip())
    result['_chosen_raw'] = chosen
    return result

def build_final_content(post):
    now_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    # Full schema markup — NewsArticle + FAQ
    schema = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle","headline":"{post['title']}","description":"{post['meta_description']}","datePublished":"{now_iso}","dateModified":"{now_iso}","keywords":"{', '.join(post.get('secondary_keywords',[]))}","author":{{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"}},"publisher":{{"@type":"Organization","name":"TrendExplained","url":"https://trendexplainednow.blogspot.com"}},"mainEntityOfPage":{{"@type":"WebPage"}}}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}}
</script>
<meta name="description" content="{post['meta_description']}"/>
<meta name="keywords" content="{post['primary_keyword']}, {', '.join(post.get('secondary_keywords', []))}"/>
<meta property="og:title" content="{post['title']}"/>
<meta property="og:description" content="{post['meta_description']}"/>
<meta property="og:type" content="article"/>
<meta name="robots" content="index, follow"/>
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

    used_topics = []
    posts_published = 0

    for i in range(3):
        print(f"\n--- Writing post {i+1} of 3 ---")
        try:
            post = write_seo_blog_post(topics, used_topics)
            used_topics.append(post.get('_chosen_raw', post['chosen_topic']))
            final_content = build_final_content(post)
            publish_to_blogger(post, final_content)
            posts_published += 1
            time.sleep(8)
        except Exception as e:
            print(f"Post {i+1} failed: {e}")
            continue

    print(f"\nDONE! Published {posts_published}/3 posts this run.")
