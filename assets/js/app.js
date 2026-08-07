
const btn = document.querySelector('.menu-toggle');
const nav = document.querySelector('#mainNav');
if (btn && nav) {
  btn.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
}
