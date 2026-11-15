import os
import json
import time
import random
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
CUSTOM_TOPIC = os.environ.get("CUSTOM_TOPIC", "").strip()
TARGET_SITE = os.environ.get("TARGET_SITE", "all").strip()

def get_active_gemini_model(api_key):
    """Dynamically discovers the active Gemini Flash/Pro model so 404 errors never happen."""
    fallback_models = ["gemini-flash-latest", "gemini-2.0-flash", "gemini-2.5-pro"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            discovered = []
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "gemini" in name:
                    if any(bad in name for bad in ["tts", "image", "embedding", "vision", "audio", "robotics", "computer-use"]):
                        continue
                    if "flash" in name:
                        discovered.insert(0, name)
                    else:
                        discovered.append(name)
            if discovered:
                return discovered
    except Exception as e:
        print("Model discovery warning:", e)
    return fallback_models

def call_gemini(api_key, prompt):
    models = get_active_gemini_model(api_key)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }).encode("utf-8")

    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                raw_text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.strip("`").removeprefix("json").strip()
                return json.loads(raw_text)
        except Exception as e:
            last_err = f"{model}: {e}"
            print("Retrying next model due to:", last_err)
    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")

def generate_post_for_site(site, topic):
    lang = site.get("lang", "Sinhala")
    if lang == "Sinhala":
        prompt = (
            f"Write a comprehensive, high-authority Sinhala Ayurveda blog post about '{topic}'. "
            "Optimize for Google SEO, ChatGPT Search, and Gemini AI Overviews (GEO). "
            "Return ONLY valid JSON with keys: "
            "slug (URL-friendly English slug), "
            "title (Sinhala title including Botanical/English name), "
            "category (one of: ඔසු පැළෑටි, ආයුර්වේද ප්‍රතිකාර, අත්බෙහෙත්), "
            "geoScore (integer 94-99), "
            "botanical (object with keys: sinhala, botanical, english, sanskrit, parts, dosha), "
            "tldr (array of 3 concise Sinhala takeaways for AI direct answers), "
            "bodyHtml (rich HTML string with h2, h3, p, ul, li tags explaining identification, Ayurvedic properties, remedies, preparation, and precautions), "
            "faqs (array of 3 objects with keys q and a in Sinhala), "
            "imagePrompt (detailed English prompt for realistic botanical photography of this herb in Sri Lanka)."
        )
    else:
        prompt = (
            f"Write a comprehensive, evidence-based English Food & Wellness blog post about '{topic}'. "
            "Optimize for Google SEO, ChatGPT Search, and Gemini AI Overviews (GEO). "
            "Return ONLY valid JSON with keys: "
            "slug (URL-friendly slug), "
            "title (SEO optimized title), "
            "category (one of: Nutrition Science, Gut Health, Healthy Recipes, Metabolic Wellness), "
            "geoScore (integer 94-99), "
            "botanical (object with keys: sinhala [Key Bioactive], botanical [Scientific/Food Source], english [Best Form], sanskrit [Nutrient Highlight], parts [Daily Serving], dosha [Metabolic Impact]), "
            "tldr (array of 3 concise summary points for AI direct answers), "
            "bodyHtml (rich HTML string with h2, h3, p, ul, li tags explaining nutritional science, health benefits, and daily usage), "
            "faqs (array of 3 objects with keys q and a), "
            "imagePrompt (detailed English prompt for bright editorial healthy food photography)."
        )

    data = call_gemini(GEMINI_API_KEY, prompt)
    seed = random.randint(1000, 99999)
    img_prompt = data.get("imagePrompt") or topic
    encoded_prompt = urllib.parse.quote(f"{img_prompt}, high resolution, editorial photography")
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1000&height=560&nologo=true&seed={seed}"

    return {
        "id": f"pending_{site['id']}_{int(time.time())}_{random.randint(100,999)}",
        "siteId": site["id"],
        "siteName": site["siteName"],
        "lang": lang,
        "slug": data.get("slug", f"post-{int(time.time())}"),
        "title": data.get("title", topic),
        "category": data.get("category", "Wellness"),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "geoScore": data.get("geoScore", 96),
        "imageUrl": img_url,
        "imagePrompt": img_prompt,
        "tldr": data.get("tldr", []),
        "botanical": data.get("botanical", {}),
        "bodyHtml": data.get("bodyHtml", ""),
        "faqs": data.get("faqs", [])
    }

def rebuild_geo_files(config, published):
    """Rebuilds llms.txt and sitemap.xml so ChatGPT, Gemini, Perplexity & Google index all published posts."""
    lines = [
        "# Multi-Site AI Discovery Index (llms.txt)",
        "> Structured knowledge index for ChatGPT (OAI-SearchBot), Google Gemini (Google-Extended), and Perplexity AI.",
        ""
    ]
    for site in config.get("sites", []):
        lines.append(f"## {site['siteName']} ({site['lang']}) - {site.get('tagline', '')}")
        site_posts = [p for p in published if p.get("siteId") == site["id"]]
        for p in site_posts:
            tldr_summary = " | ".join(p.get("tldr", [])[:2])
            bot_name = p.get("botanical", {}).get("botanical", "")
            lines.append(f"- [{p['title']}](/{site['folder']}/?post={p.get('slug', p['id'])}) [{bot_name}]: {tldr_summary}")
        lines.append("")

    with open("llms.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Build sitemap.xml
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in published:
        folder = p.get("siteId", "helaosu")
        slug = p.get("slug", p["id"])
        date = p.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
        xml.append(f"  <url><loc>/{folder}/?post={slug}</loc><lastmod>{date}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>")
    xml.append("</urlset>")

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

def main():
    with open("data/sites_config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    with open("data/pending_posts.json", "r", encoding="utf-8") as f:
        pending = json.load(f)
    with open("data/published_posts.json", "r", encoding="utf-8") as f:
        published = json.load(f)

    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY secret not set yet. Rebuilding GEO files only.")
        rebuild_geo_files(config, published)
        return

    for site in config.get("sites", []):
        if TARGET_SITE not in ("all", "", site["id"]):
            continue

        if CUSTOM_TOPIC:
            topics_to_run = [CUSTOM_TOPIC]
        else:
            quota = int(site.get("dailyQuota", 4))
            suggestions = site.get("suggestions", [])
            topics_to_run = []
            for _ in range(quota):
                if suggestions:
                    topics_to_run.append(suggestions.pop(0))
                else:
                    default_t = "දේශීය ආයුර්වේද ඔසු පැළෑටියක ගුණ සහ ප්‍රතිකාර" if site["lang"] == "Sinhala" else "Evidence-based daily nutrition and longevity habit"
                    topics_to_run.append(default_t)
            site["suggestions"] = suggestions

        for topic in topics_to_run:
            print(f"Generating [{site['siteName']}] -> {topic}")
            try:
                new_post = generate_post_for_site(site, topic)
                pending.insert(0, new_post)
                time.sleep(2)
            except Exception as e:
                print(f"Error generating '{topic}':", e)

    with open("data/sites_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    with open("data/pending_posts.json", "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    rebuild_geo_files(config, published)
    print("Successfully generated daily posts and updated GEO index.")

if __name__ == "__main__":
    main()
