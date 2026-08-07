// Ideiglenes karbantartási mód.
// A publikus látogatók csak a maintenance oldalt látják.
// A rejtett preview.html megnyitása az adott böngészőfülre engedélyezi az előnézetet.
(function () {
  const localHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0"]);
  const isLocal = localHosts.has(window.location.hostname);
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const isPreviewEntry = path.endsWith("/preview.html") || path === "/preview.html";

  if (isPreviewEntry) {
    try { sessionStorage.setItem("fehervital_preview", "1"); } catch (_) {}
  }

  let previewActive = false;
  try { previewActive = sessionStorage.getItem("fehervital_preview") === "1"; } catch (_) {}

  const isMaintenancePage = path === "/" || path.endsWith("/index.html");
  if (!isLocal && !previewActive && !isMaintenancePage) {
    window.location.replace("/");
    return;
  }

  if (previewActive) {
    document.addEventListener("DOMContentLoaded", () => {
      document.querySelectorAll('a[href="index.html"], a[href="/"]').forEach((link) => {
        link.setAttribute("href", "preview.html");
      });
    });
  }
})();


function cmsApplyDesign(site) {
  const d = site?.design || {};
  const root = document.documentElement;
  if (d.primary) root.style.setProperty('--primary', d.primary);
  if (d.secondary) root.style.setProperty('--primary-dark', d.secondary);
  if (d.background) root.style.setProperty('--bg', d.background);
  if (d.text) root.style.setProperty('--ink', d.text);
  if (d.radius) root.style.setProperty('--radius', `${Number(d.radius)||18}px`);
  if (d.font === 'serif') document.body.style.fontFamily = 'Georgia, "Times New Roman", serif';
  else if (d.font === 'humanist') document.body.style.fontFamily = 'Trebuchet MS, Arial, sans-serif';
  else document.body.style.fontFamily = 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

  if (d.shadow === 'none') root.style.setProperty('--shadow', 'none');
  else if (d.shadow === 'strong') root.style.setProperty('--shadow', '0 18px 50px rgba(20,45,34,.18)');
  else root.style.setProperty('--shadow', '0 10px 30px rgba(20,45,34,.10)');
}

function cmsSetMeta(name, content, property=false) {
  if (!content) return;
  let sel = property ? `meta[property="${name}"]` : `meta[name="${name}"]`;
  let el = document.head.querySelector(sel);
  if (!el) {
    el = document.createElement('meta');
    if (property) el.setAttribute('property', name); else el.setAttribute('name', name);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}

function cmsApplySEO(page) {
  const seo = page?.seo || {};
  if (seo.title) document.title = seo.title;
  cmsSetMeta('description', seo.description || '');
  cmsSetMeta('keywords', seo.keywords || '');
  cmsSetMeta('og:title', seo.title || document.title, true);
  cmsSetMeta('og:description', seo.description || '', true);
  if (seo.og_image) cmsSetMeta('og:image', new URL(seo.og_image, location.href).href, true);
}

function cmsApplyContact(site) {
  const c = site?.contact || {};
  document.querySelectorAll('[data-cms-contact="phone"]').forEach(el => el.textContent = c.phone || '');
  document.querySelectorAll('[data-cms-contact="email"]').forEach(el => el.textContent = c.email || '');
  document.querySelectorAll('[data-cms-contact="address"]').forEach(el => el.textContent = c.address || '');
}


function cmsApplySiteSettings(data) {
  const site = data?.site || {};
  cmsApplyDesign(site);
  cmsApplyContact(site);

  // Márkanév / logó
  document.querySelectorAll('.brand').forEach(el => {
    if (site.logo_image) {
      el.innerHTML = '';
      const img = document.createElement('img');
      img.src = site.logo_image;
      img.alt = site.logo_text || 'Fehérvitál';
      img.className = 'cms-site-logo';
      el.appendChild(img);
    } else if (site.logo_text) {
      el.textContent = site.logo_text;
    }
  });

  // Favicon
  if (site.favicon) {
    let link = document.querySelector('link[rel="icon"]');
    if (!link) {
      link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.href = site.favicon;
  }

  // Főoldali hero média
  const heroMount = document.querySelector('[data-cms-hero-media]');
  if (heroMount) {
    heroMount.innerHTML = '';
    const hm = site.hero_media || {};
    if (hm.type === 'image' && hm.src) {
      const img = document.createElement('img');
      img.src = hm.src;
      img.alt = hm.alt || '';
      img.className = 'cms-hero-media';
      heroMount.appendChild(img);
    } else if (hm.type === 'video' && hm.src) {
      const embed = cmsYoutubeEmbed(hm.src) || cmsVimeoEmbed(hm.src);
      if (embed) {
        const iframe = document.createElement('iframe');
        iframe.src = embed;
        iframe.title = hm.alt || 'Fehérvitál videó';
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        iframe.allowFullscreen = true;
        iframe.className = 'cms-hero-media cms-hero-video';
        heroMount.appendChild(iframe);
      } else {
        const video = document.createElement('video');
        video.src = hm.src;
        video.controls = true;
        video.preload = 'metadata';
        video.className = 'cms-hero-media';
        heroMount.appendChild(video);
      }
    }
    heroMount.classList.toggle('cms-hero-empty', !heroMount.children.length);
  }

  // Főoldali galéria
  const galleryMount = document.querySelector('[data-cms-gallery]');
  if (galleryMount) {
    galleryMount.innerHTML = '';
    (site.gallery || []).filter(x => x && x.src).forEach(item => {
      const figure = document.createElement('figure');
      figure.className = 'cms-gallery-item';
      const img = document.createElement('img');
      img.src = item.src;
      img.alt = item.alt || '';
      img.loading = 'lazy';
      figure.appendChild(img);
      if (item.caption) {
        const cap = document.createElement('figcaption');
        cap.textContent = item.caption;
        figure.appendChild(cap);
      }
      galleryMount.appendChild(figure);
    });
    galleryMount.closest('.cms-gallery-section')?.classList.toggle('cms-empty', !galleryMount.children.length);
  }
}

const btn = document.querySelector('.menu-toggle');
const nav = document.querySelector('#mainNav');
if (btn && nav) {
  btn.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
}

function cmsYoutubeEmbed(url) {
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname.includes('youtu.be')) {
      const id = u.pathname.replace(/^\//, '').split('/')[0];
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null;
    }
    if (u.hostname.includes('youtube.com')) {
      const id = u.searchParams.get('v');
      if (id) return `https://www.youtube-nocookie.com/embed/${id}`;
      const parts = u.pathname.split('/').filter(Boolean);
      if (parts[0] === 'shorts' && parts[1]) return `https://www.youtube-nocookie.com/embed/${parts[1]}`;
      if (parts[0] === 'embed' && parts[1]) return `https://www.youtube-nocookie.com/embed/${parts[1]}`;
    }
  } catch (_) {}
  return null;
}
function cmsVimeoEmbed(url) {
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname.includes('vimeo.com')) {
      const id = u.pathname.split('/').filter(Boolean).find(x => /^\d+$/.test(x));
      return id ? `https://player.vimeo.com/video/${id}` : null;
    }
  } catch (_) {}
  return null;
}
function cmsParagraphs(container, text) {
  String(text || '').split(/\n{2,}/).forEach(part => {
    if (!part.trim()) return;
    const p = document.createElement('p'); p.textContent = part.trim(); container.appendChild(p);
  });
}
function cmsApplyLayout(wrap, block) {
  const width = ['50','75','100'].includes(String(block.width)) ? String(block.width) : '100';
  wrap.classList.add(`cms-width-${width}`);
  if (block.align === 'center') wrap.classList.add('cms-align-center');
  if (block.style === 'highlight') wrap.classList.add('cms-highlight');
}
function cmsRenderBlock(block) {
  const wrap = document.createElement('article');
  wrap.className = `cms-block cms-block-${block.type || 'text'}`;
  cmsApplyLayout(wrap, block);

  if (block.type === 'text') {
    if (block.heading) {
      const h = document.createElement(block.level === 3 ? 'h3' : 'h2'); h.textContent = block.heading; wrap.appendChild(h);
    }
    cmsParagraphs(wrap, block.text);
  } else if (block.type === 'image') {
    const figure = document.createElement('figure'); figure.className = 'cms-media';
    const img = document.createElement('img'); img.src = block.src || ''; img.alt = block.alt || ''; img.loading = 'lazy';
    if (block.link) {
      const a = document.createElement('a'); a.href = block.link; a.target = '_blank'; a.rel = 'noopener'; a.appendChild(img); figure.appendChild(a);
    } else figure.appendChild(img);
    if (block.caption) { const cap=document.createElement('figcaption'); cap.textContent=block.caption; figure.appendChild(cap); }
    wrap.appendChild(figure);
  } else if (block.type === 'iconbox') {
    wrap.classList.add('cms-iconbox');
    const icon = document.createElement('div');
    icon.className = 'cms-icon';
    icon.textContent = block.icon || '✓';
    wrap.appendChild(icon);
    if (block.heading) {
      const h = document.createElement('h3'); h.textContent = block.heading; wrap.appendChild(h);
    }
    cmsParagraphs(wrap, block.text);
  } else if (block.type === 'testimonial') {
    wrap.classList.add('cms-testimonial');
    const q = document.createElement('blockquote'); q.textContent = block.text || ''; wrap.appendChild(q);
    if (block.author) {
      const a = document.createElement('div'); a.className = 'cms-testimonial-author'; a.textContent = block.author; wrap.appendChild(a);
    }
  } else if (block.type === 'price') {
    wrap.classList.add('cms-price');
    const h = document.createElement('h3'); h.textContent = block.heading || ''; wrap.appendChild(h);
    const pr = document.createElement('div'); pr.className='cms-price-value'; pr.textContent = block.price || ''; wrap.appendChild(pr);
    cmsParagraphs(wrap, block.text);
  } else if (block.type === 'divider') {
    wrap.classList.add('cms-divider'); wrap.appendChild(document.createElement('hr'));
  } else if (block.type === 'buttons') {
    wrap.classList.add('cms-buttons');
    (block.buttons || []).forEach(btn => {
      const a = document.createElement('a');
      a.className = 'btn';
      a.href = btn.url || '#';
      a.textContent = btn.label || 'Gomb';
      if (btn.new_tab) { a.target='_blank'; a.rel='noopener'; }
      wrap.appendChild(a);
    });
  } else if (block.type === 'video') {
    const figure = document.createElement('figure'); figure.className='cms-media cms-video';
    const embed = cmsYoutubeEmbed(block.src || '') || cmsVimeoEmbed(block.src || '');
    if (embed) {
      const frame=document.createElement('iframe'); frame.src=embed; frame.title=block.title||'Videó'; frame.loading='lazy';
      frame.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'; frame.allowFullscreen=true; figure.appendChild(frame);
    } else {
      const video=document.createElement('video'); video.src=block.src||''; video.controls=true; video.preload='metadata'; figure.appendChild(video);
    }
    if(block.caption){const cap=document.createElement('figcaption');cap.textContent=block.caption;figure.appendChild(cap)}
    wrap.appendChild(figure);
  } else if (block.type === 'cta') {
    const box=document.createElement('div'); box.className='cms-cta-box';
    if(block.heading){const h=document.createElement('h2');h.textContent=block.heading;box.appendChild(h)}
    if(block.text){const p=document.createElement('p');p.textContent=block.text;box.appendChild(p)}
    if(block.buttonText && block.url){const a=document.createElement('a');a.className='btn';a.href=block.url;a.textContent=block.buttonText;box.appendChild(a)}
    wrap.appendChild(box);
  } else if (block.type === 'faq') {
    if(block.heading){const h=document.createElement('h2');h.textContent=block.heading;wrap.appendChild(h)}
    const list=document.createElement('div'); list.className='cms-faq-list';
    (block.items||[]).forEach(item=>{if(!item.question&&!item.answer)return; const d=document.createElement('details'); const s=document.createElement('summary');s.textContent=item.question||'Kérdés'; d.appendChild(s); const p=document.createElement('p');p.textContent=item.answer||'';d.appendChild(p);list.appendChild(d)});
    wrap.appendChild(list);
  }
  return wrap;
}
function cmsDataUrl() {
  try {
    const u = new URL(window.location.href);
    if (u.searchParams.get('cms_preview') === '1') return '/__admin/preview-content';
  } catch (_) {}
  return 'assets/content/pages.json';
}

async function cmsLoadPage() {
  const mount=document.querySelector('[data-cms-page]'); if(!mount)return;
  const slug=mount.dataset.cmsPage;
  try {
    const res=await fetch('assets/content/pages.json',{cache:'no-store'}); if(!res.ok)return;
    const data=await res.json(); const page=data?.pages?.[slug];
    if(!page||page.enabled===false){mount.closest('.cms-content-section')?.classList.add('cms-empty');return}
    (page.fields||[]).forEach(field=>{
      document.querySelectorAll(`[data-cms-field="${CSS.escape(field.key)}"]`).forEach(el=>{el.textContent=field.value??''});
    });
    const blocks=(page.blocks||[]).filter(b=>b&&b.visible!==false);
    if(!blocks.length){mount.closest('.cms-content-section')?.classList.add('cms-empty');return}
    mount.replaceChildren(...blocks.map(cmsRenderBlock));
  } catch(err){console.warn('CMS tartalom nem tölthető be:',err)}
}
cmsLoadPage();


async function cmsLoadSiteOnly() {
  if (document.querySelector('[data-cms-page]')) return;
  try {
    const res = await fetch(cmsDataUrl(), {cache: 'no-store'});
    if (!res.ok) return;
    cmsApplySiteSettings(await res.json());
  } catch (_) {}
}
cmsLoadSiteOnly();
