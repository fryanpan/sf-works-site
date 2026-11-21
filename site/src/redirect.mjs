// A page that only sends the reader on, for an address that has moved. The
// build keeps any module exporting `redirect` out of the sitemap.

/** A redirect page to `to`, naming where the reader is going. The script
 * carries the query string on, which the board's frame needs: its ?cw-frame=1
 * is what lets the framed page run scripts, and a meta refresh drops it. The
 * meta refresh stays for readers without JavaScript. */
export function redirectPage(to, name) {
  const canonical = to.split("#")[0];
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url=${to}">
<script>(function(){var m=document.querySelector('meta[http-equiv="refresh"]'),c=m.content,t=c.slice(c.indexOf("url=")+4),q=location.search;if(q)t=t.replace(/(#|$)/,function(h){return(t.indexOf("?")<0?q:"&"+q.slice(1))+h;});if(location.hash&&t.indexOf("#")<0)t+=location.hash;location.replace(t);})();</script>
<link rel="canonical" href="${canonical}">
<meta name="robots" content="noindex">
<title>Moved — SF Works</title>
</head>
<body>
<p>This page has moved to <a href="${to}">${name}</a>.</p>
</body>
</html>
`;
}
