# SecureShelf — বাস্তবায়ন পরিকল্পনা

## পণ্য ও বাস্তবায়ন

SecureShelf হলো আপলোড করা HackingTool source archive-কে নিরাপদ, read-only cybersecurity resource directory-তে ব্যবহারযোগ্য করে তোলার একটি responsive web application। ZIP-এর পুরো contents আলাদাভাবে `upstream/hackingtool-master/`-এ সংরক্ষিত থাকবে; app metadata হবে `docs/TOOLS.md`-এর curated তালিকা থেকে, যাতে প্রতিটি listing-এর নাম, category, tags এবং সত্যিই দেওয়া থাকলে upstream URL থাকে। Official URL অনুপস্থিত হলে সেটি বানিয়ে না দিয়ে অনুপস্থিত বলে দেখাতে হবে। UI-তে কোনো script, shell command বা exploit চালানো হবে না; source archive-টিও কোনো server-side runner-এ connect করা হবে না।

প্রথম সংস্করণ সম্পূর্ণ static: HTML, CSS, vanilla JavaScript, JSON catalog এবং catalog পুনর্নির্মাণের জন্য standard-library Python script। Login, database, external API বা secrets লাগবে না। Search নাম/category/tag-এ কাজ করবে; category, resource type, tag এবং saved-only filter একসঙ্গে প্রয়োগ হবে; filter reset, result count, paging, details dialog, official-source link, clipboard copy এবং browser-local bookmarks থাকবে। Scope ও authorization সতর্কতা স্থায়ীভাবে দৃশ্যমান থাকবে। Accessible native controls, keyboard operation, focus management, reduced-motion preference এবং mobile layout ব্যবহার করা হবে। Preview-তে Python static-file server port 3000-এ পরিবেশন করবে; Vercel/Render-এর জন্য static output-ই যথেষ্ট, deployment credentials এখন দরকার নেই।

## Project structure

- `index.html` — একমাত্র application route; metadata, filter controls, catalog view, details dialog ও safety notice।
- `assets/styles.css` — responsive design system, grid/list states, accessibility ও motion rules।
- `assets/app.js` — catalog fetch/render, search/filter/sort, paging, saved IDs, dialog ও keyboard behavior।
- `data/catalog.json` — source Markdown থেকে তৈরি read-only resource records।
- `scripts/build_catalog.py` — upstream Markdown থেকে JSON metadata পুনরায় তৈরি করার নিরাপদ standard-library script; কোনো tool code import/run করে না।
- `scripts/serve.py` — local/Preview-র জন্য static-file-only Python server; কোনো command execution, dynamic API বা database নেই।
- `public/manus-routes.json` — declared page route।
- `assets/mark.svg` — custom text-free SecureShelf mark এবং favicon।
- `upstream/hackingtool-master/` — user-এর ZIP থেকে সম্পূর্ণ unmodified extracted source; app runtime থেকে বিচ্ছিন্ন।

## ডিজাইন

সম্ভাব্য দিক: (১) Swiss typographic resource ledger — 0.08; (২) নরম newsroom editorial directory — 0.06; (৩) neon cyberpunk console — 0.04। বেছে নেওয়া দিক: Swiss typographic ledger, যাতে ঘন tool metadata পড়া যায় এবং decoration-এর চেয়ে hierarchy-কে অগ্রাধিকার দেওয়া হয়।

- **Design Movement:** Swiss International Typographic Style, incident-response catalog-এর সংযত operational tone-সহ।
- **Core Principles:** স্পষ্ট information hierarchy; source attribution দৃশ্যমান; ঝুঁকি ও authorization প্রসঙ্গ লুকানো নয়; filter state সবসময় বোঝা যায়।
- **Color Philosophy:** গাঢ় ink/navy পটভূমি আস্থার ও focus-এর জন্য, off-white reading surface দীর্ঘ catalog browsing-এর জন্য, এবং signal-lime শুধু active state/primary action-এ—সতর্কবার্তাকে রঙের গর্জনে ঢেকে না রেখে।
- **Layout Paradigm:** বাম পাশে compact category rail, মাঝখানে宽 catalog canvas, উপরে fixed-context search/filter toolbar; ছোট পর্দায় rail horizontal scroll/chips-এ রূপ নেবে।
- **Signature Elements:** ক্ষুদ্র monospaced category IDs; lime status ticks; structured metadata rows ও hairline rules।
- **Interaction Philosophy:** সব state reversible; filter স্পষ্টভাবে দেখায় কেন কোনো result দেখা যাচ্ছে; কোনো click-ই resource চালায় না—details dialog-এ তথ্য, bookmark ও source link থাকে।
- **Animation:** শুধু ছোট opacity/translate transitions; `prefers-reduced-motion`-এ বন্ধ; loading-এর জন্য অপ্রয়োজনীয় skeleton shimmer নয়।
- **Typography System:** system sans-serif body, compact headings; metadata ও taxonomy-তে system monospace; mobile-এ অন্তত 16px body/search text।
- **Brand Essence:** অনুমোদিত security learning ও assessment-এর জন্য source-linked, browsable directory; personality: সংযত, নির্ভরযোগ্য, সতর্ক।
- **Brand Voice:** ছোট, নির্দিষ্ট, দায়িত্বশীল। উদাহরণ: “খুঁজুন, যাচাই করুন, scope মেনে চলুন।” / “এই directory কোনো tool চালায় না।”
- **Wordmark & Logo:** চার কোণ-চিহ্নে ঘেরা একটি ছোট `S`/shelf-line motif, inline SVG mark; wordmark custom weight ও ছোট source label-সহ।
- **Signature Brand Color:** signal lime `#C8F36A`।

## নির্ভরতা ও serving

Build/dependency install নেই। Python 3-এর standard library কেবল metadata JSON rebuild ও static Preview serving-এর জন্য। Production deployment-এ static host-এ project root সরাসরি serve করা যাবে; Python service বাধ্যতামূলক নয়। Bookmarks শুধু browser `localStorage`-এ থাকবে, কোনো external transmission নেই।