const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const { createWorker, PSM } = require('tesseract.js');

const catalogPath = path.join('sources', 'bho', 'catalog.json');

function countDevanagari(text) {
  const matches = text.match(/[\u0900-\u097F]/g);
  return matches ? matches.length : 0;
}

function cleanText(text) {
  return text
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function preprocess(imagePath, variant) {
  const image = sharp(imagePath);
  const meta = await image.metadata();
  const cropHeight = Math.floor(meta.height * variant.cropRatio);

  let pipeline = sharp(imagePath)
    .extract({ left: 0, top: 0, width: meta.width, height: cropHeight })
    .grayscale()
    .normalise();

  if (variant.negate) {
    pipeline = pipeline.negate();
  }

  return pipeline
    .resize({ width: meta.width * variant.scale })
    .threshold(variant.threshold)
    .toBuffer();
}

function variantsForPage(pageNumber) {
  if (pageNumber <= 2) {
    return [
      { name: 'invert-credits', cropRatio: 0.82, negate: true, threshold: 140, scale: 3 },
      { name: 'normal-credits', cropRatio: 0.82, negate: false, threshold: 170, scale: 3 },
    ];
  }

  return [
    { name: 'normal-body', cropRatio: 0.72, negate: false, threshold: 175, scale: 3 },
    { name: 'invert-body', cropRatio: 0.80, negate: true, threshold: 140, scale: 3 },
    { name: 'wide-body', cropRatio: 0.88, negate: false, threshold: 175, scale: 3 },
  ];
}

async function recognizePage(worker, imagePath, pageNumber) {
  let best = { text: '', score: -1, variant: '' };

  for (const variant of variantsForPage(pageNumber)) {
    const buffer = await preprocess(imagePath, variant);
    const result = await worker.recognize(buffer);
    const text = cleanText(result.data.text || '');
    const score = countDevanagari(text) + Math.max(0, Math.floor((result.data.confidence || 0) / 5));

    if (score > best.score) {
      best = { text, score, variant: variant.name };
    }
  }

  return best;
}

async function main() {
  const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
  const worker = await createWorker('hin');
  await worker.setParameters({ tessedit_pageseg_mode: PSM.AUTO });

  for (const story of catalog) {
    const storyDir = path.join('sources', 'bho', story.slug);
    const manifestPath = path.join(storyDir, 'manifest.json');
    if (!fs.existsSync(manifestPath)) {
      continue;
    }

    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    const lines = [
      `Source URL: https://media.ipsapps.org/b4child/osa/bho/${story.ref}`,
      `Story: ${story.title}`,
      'OCR: tesseract.js (hin), preprocessed from image-only source',
      '',
    ];

    for (const page of manifest.pages) {
      const pageMatch = (page.page_counter || '').match(/^(\d+)\//);
      const pageNumber = pageMatch ? Number(pageMatch[1]) : 0;
      const imagePath = page.local_image_path.replace(/\//g, path.sep);
      const best = await recognizePage(worker, imagePath, pageNumber);

      lines.push(`[Page ${pageNumber || page.page_counter}]`);
      lines.push(best.text || '[no text recognized]');
      lines.push('');
    }

    fs.writeFileSync(path.join(storyDir, 'text.txt'), lines.join('\n'), 'utf8');
  }

  await worker.terminate();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
