// Site analytics — currently OFF. The app has none and never will; this file
// only ever affects this website.
//
// To switch it on, uncomment ONE block below and fill in the id. Nothing else
// in the site needs to change: every page already loads this file.
//
// Recommended: Umami Cloud (free tier, cookieless, no consent banner, and it
// supports the custom events we actually need — which is why Cloudflare Web
// Analytics was ruled out: it has no custom events and no UTM reporting).
//
//   const s = document.createElement('script');
//   s.defer = true;
//   s.src = 'https://cloud.umami.is/script.js';
//   s.dataset.websiteId = 'PASTE-WEBSITE-ID-HERE';
//   document.head.appendChild(s);
//
// Alternative: GA4, if the familiar dashboard is worth the cookie banner.
//
//   const s = document.createElement('script');
//   s.async = true;
//   s.src = 'https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX';
//   document.head.appendChild(s);
//   window.dataLayer = window.dataLayer || [];
//   function gtag(){dataLayer.push(arguments);}
//   gtag('js', new Date());
//   gtag('config', 'G-XXXXXXXXXX');
//
// Note: the highest-value conversion on this site does not need any of this.
// Every "get listed" call to action is a mailto with its own subject line, so
// the inbox is already the conversion counter.
