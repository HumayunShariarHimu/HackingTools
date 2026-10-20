# SecureShelf — Cybersecurity Resource Library

SecureShelf হলো cybersecurity tools, learning resources ও upstream source-এর জন্য একটি Bengali-first, responsive, read-only directory। Search, category/type/tag filters, details, official-source links, browser-local bookmarks এবং explicit authorization guidance আছে। এই app কোনো tool/script/command চালায় না এবং কোনো backend/API key প্রয়োজন হয় না।

## Local preview

Python 3-এর standard library ছাড়া কোনো dependency লাগে না। Repo root থেকে:

```bash
python3 scripts/serve.py
```

তারপর `http://localhost:3000` খুলুন। Catalog JSON আবার তৈরি করতে:

```bash
python3 scripts/build_catalog.py
```

## Static build / deployment

```bash
python3 scripts/build_catalog.py
python3 scripts/build_site.py
```

Static output `dist/`-এ তৈরি হয়। Vercel-এ static deployment-এর জন্য build command `python3 scripts/build_catalog.py && python3 scripts/build_site.py` এবং output directory `dist` দিন। Render-এ **Static Site** ব্যবহার করুন—build command একই, publish directory `dist`; এই app-এর জন্য Render Web Service/backend দরকার নেই। কোনো secrets বা environment variables লাগবে না। Preview server আলাদা, static hosting output-এ সেটি চালানোর প্রয়োজন নেই।

## Catalog provenance

সম্পূর্ণ user-provided ZIP source `upstream/hackingtool-master/`-এ রাখা হয়েছে। Website metadata কেবল archived `docs/TOOLS.md` থেকে নাম, category, tags এবং সেখানে সরাসরি দেওয়া HTTPS source URL-গুলো পড়ে তৈরি হয় (`data/catalog.json`)। `python3 scripts/build_catalog.py` metadata-ийг পুনরায় তৈরি করে; archived tool modules import বা execute করে না। Source link না থাকলে directory সেটি অনুপস্থিত বলে দেখায়; platform-ও archive-এ উল্লেখ না থাকলে অনুমান করে না।

Archived README 219টি active tool-এর কথা বলে, কিন্তু প্রকাশিত `docs/TOOLS.md`-এ এই builder 215টি entry পায়। App-এ গণনাকৃত 215টি metadata record দেখানো হয় এবং README-এর সংখ্যার সঙ্গে পার্থক্যটি জানানো হয়—missing entry বা link উদ্ভাবন করা হয়নি।

Upstream project ও copyright/license notice: [`upstream/hackingtool-master/README.md`](upstream/hackingtool-master/README.md), [`upstream/hackingtool-master/LICENSE`](upstream/hackingtool-master/LICENSE), এবং upstream [HackingTool repository](https://github.com/Z4nzu/hackingtool)। Original archive অপরিবর্তিতভাবে রাখা হয়েছে।

## নিরাপদ ব্যবহার

সব resource কেবল নিজের system বা স্পষ্ট লিখিত অনুমতি ও নির্দিষ্ট scope-এ পরীক্ষা করার জন্য। Phishing, denial-of-service, credential, exploitation, wireless ও post-exploitation বিষয়ের তালিকাগুলো সতর্কতামূলক context-সহ প্রদর্শিত হয়; list থাকা মানে endorsement নয়। Production code-এ কোনো archived tool execution path বা command runner নেই। Link খোলার আগে official project, license, publisher এবং সম্ভাব্য প্রভাব যাচাই করুন।

## Files

- `index.html`, `assets/styles.css`, `assets/app.js` — static Bengali web application.
- `data/catalog.json` — build করা metadata-only catalog.
- `scripts/build_catalog.py` — upstream Markdown থেকে catalog builder.
- `scripts/build_site.py` — `dist/` static output builder.
- `scripts/serve.py` — local/Preview static-file server.
- `upstream/hackingtool-master/` — সম্পূর্ণ uploaded ZIP extraction.
