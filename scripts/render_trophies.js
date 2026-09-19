// Rebuild newsletter trophy assets with Node and sharp (npm install sharp).
// PNGs keep the metal colors and rotation consistent in email clients.
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const output = path.join(__dirname, '..', 'assets', 'newsletter');
const palettes = {
  gold: ['#FFF1B8', '#E8BD59', '#AD7623', '#6F491B'],
  silver: ['#F4F8FC', '#CED8E3', '#8295A8', '#475D73'],
  bronze: ['#F5D0A5', '#CD935F', '#9F6235', '#633B24'],
};

async function render() {
  fs.mkdirSync(output, { recursive: true });
  for (const [metal, [light, mid, dark, edge]] of Object.entries(palettes)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="144" viewBox="0 0 120 144">
      <defs>
        <linearGradient id="metal"><stop stop-color="${dark}"/><stop offset=".28" stop-color="${light}"/>
          <stop offset=".55" stop-color="${mid}"/><stop offset="1" stop-color="${dark}"/></linearGradient>
      </defs>
      <g fill="none" stroke="${dark}" stroke-width="5">
        <path d="M34 28H17v13c0 18 13 27 26 27M86 28h17v13c0 18-13 27-26 27"/>
      </g>
      <g fill="none" stroke="${light}" stroke-width="1.5">
        <path d="M32 28H17v13c0 18 13 27 26 27M88 28h15v13c0 18-13 27-26 27"/>
      </g>
      <path d="M30 19h60l-4 31c-2 20-12 31-26 34-14-3-24-14-26-34Z"
        fill="url(#metal)" stroke="${edge}" stroke-width="1.4"/>
      <path d="M39 27l3 25c1 12 7 21 13 24" fill="none" stroke="${light}" stroke-width="2" opacity=".7"/>
      <rect x="28" y="16" width="64" height="7" rx="3" fill="url(#metal)" stroke="${edge}"/>
      <path d="M55 83h10v20c0 6 7 9 15 11H40c8-2 15-5 15-11Z" fill="url(#metal)" stroke="${edge}"/>
      <ellipse cx="60" cy="114" rx="23" ry="4" fill="url(#metal)" stroke="${edge}"/>
      <rect x="34" y="118" width="52" height="13" rx="2" fill="#142B3D"/>
      <rect x="30" y="130" width="60" height="5" rx="1.5" fill="#233E52"/>
      <rect x="48" y="121" width="24" height="6" rx="1" fill="url(#metal)"/>
      <path d="m60 38 3 7 8 .7-6 5 2 8-7-4-7 4 2-8-6-5 8-.7Z" fill="${light}" stroke="${dark}" stroke-width=".8"/>
    </svg>`;
    const image = await sharp(Buffer.from(svg)).resize(360, 432).png().toBuffer();
    fs.writeFileSync(path.join(output, `trophy-${metal}.png`), image);
    if (metal === 'gold') {
      await sharp(image).rotate(180).png().toFile(path.join(output, 'trophy-upside-down.png'));
    }
  }
}
render().catch(error => { console.error(error); process.exitCode = 1; });
