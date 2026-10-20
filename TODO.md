# কাজের অগ্রগতি

## সম্পূর্ণ

- [x] **সম্পূর্ণ ZIP source repository-তে রাখা** — “শুধুমাত্র total যে zip তা সেটি unzip করে আমার repository তে সবার আগে push করো” এবং “আগে সবার প্রথমে unzip করে সবকিছু আগে full repository তে নাও, তারপর development নিশ্চিত করো।” ZIP যাচাই করে সব ফাইল `upstream/hackingtool-master/`-এ extract করে requested public GitHub repository-র `main` branch-এ development শুরুর আগে push করা হয়েছে। Commit: `753d30f`.

## বাকি

- [ ] **সার্চযোগ্য ও filterable resource directory** — ZIP-এর cybersecurity tools metadata ও files পর্যালোচনা করে নিরাপদ resource catalog তৈরি; নাম, description, keyword ও relevant metadata দিয়ে দ্রুত search; Category-based browsing এবং category filter; Tool type, platform বা অন্যান্য archive-উপযোগী attributes অনুযায়ী filter ও clear-filter controls।
- [ ] **Resource details ও নিরাপদ ব্যবহার** — প্রতিটি resource-এর purpose, key details, category, platform এবং ব্যবহার-সংক্রান্ত তথ্যসহ detail view; প্রতিটি listing-এ যাচাইযোগ্য trusted upstream বা official source link; Catalog ও resource detail-এ authorization, legal scope এবং safe-use guidance স্পষ্টভাবে প্রদর্শন।
- [ ] **কাজের responsive web interface** — Responsive, mobile-friendly catalog navigation এবং accessible interface; search, filters ও detail control keyboard-এ ব্যবহারযোগ্য।
- [ ] **নিরাপদ static architecture ও repository docs** — Offensive বা dual-use scripts-এর automatic browser/server execution বন্ধ রেখে read-only directory behavior; `index.html`, CSS, JavaScript ও প্রয়োজনীয় Python source-সহ GitHub repository-ready project structure; archive source unmodified অবস্থায় সংরক্ষিত ও attribution/license দৃশ্যমান।