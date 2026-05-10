#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const chapterFilePattern = /^CHAPTER_(\d+)\.from_([^.]+)\.md$/;
const verseLinePattern = /^\*\*(\d+)\*\*\s+(.+)$/;

const openAiModel = "gpt-4o-mini-tts";
const openAiVoice = "onyx";
const toneProfile = "male, serious, reverent, lower, fuller, subtle groove";
const languageConfig = {
  bho: {
    versePrefix: "पद",
    instructions:
      "Narrate scripture with a male voice and a serious, reverent tone. Keep the delivery lower, fuller, and steady, with a subtle groove rather than a bright conversational feel. Read Devanagari naturally and keep each verse number clearly audible.",
  },
  ptb: {
    versePrefix: "Versículo",
    instructions:
      "Narrate scripture in Brazilian Portuguese with a male voice and a serious, reverent tone. Keep the delivery lower, fuller, and steady, with a subtle groove rather than a bright conversational feel. Read each verse number clearly.",
  },
};

function parseArgs(argv) {
  const options = {
    language: "bho",
    bookFolder: "01_GEN",
    source: "wtm",
    overwrite: false,
    maxChunkCharacters: 3600,
  };

  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--overwrite") {
      options.overwrite = true;
      continue;
    }

    const next = argv[index + 1];
    if (!next) {
      throw new Error(`Missing value for ${arg}`);
    }

    if (arg === "--language") {
      options.language = next;
    } else if (arg === "--book-folder") {
      options.bookFolder = next;
    } else if (arg === "--source") {
      options.source = next;
    } else if (arg === "--chapter") {
      options.chapter = Number.parseInt(next, 10);
      if (!Number.isInteger(options.chapter)) {
        throw new Error(`Invalid chapter: ${next}`);
      }
    } else if (arg === "--max-chunk-characters") {
      options.maxChunkCharacters = Number.parseInt(next, 10);
      if (!Number.isInteger(options.maxChunkCharacters) || options.maxChunkCharacters < 500) {
        throw new Error(`Invalid --max-chunk-characters value: ${next}`);
      }
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }

    index += 1;
  }

  return options;
}

function readOpenAiApiKeyFromText(text) {
  const patterns = [
    /OPENAI_API_KEY\s*[:=]\s*"([^"]+)"/,
    /OPENAI_API_KEY\s*[:=]\s*'([^']+)'/,
    /OPENAI_API_KEY\s*[:=]\s*([^\r\n#]+)/,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      return match[1].trim();
    }
  }

  return null;
}

function getOpenAiApiKey() {
  if (process.env.OPENAI_API_KEY) {
    return process.env.OPENAI_API_KEY;
  }

  for (const candidate of [
    path.join(repoRoot, "secrets.yaml"),
    path.join(repoRoot, ".env"),
    path.join(__dirname, "secrets.yaml"),
  ]) {
    if (!fs.existsSync(candidate)) {
      continue;
    }

    const value = readOpenAiApiKeyFromText(fs.readFileSync(candidate, "utf8"));
    if (value) {
      return value;
    }
  }

  return null;
}

function findChapterFiles(options) {
  const inputDir = path.join(repoRoot, "text", options.language, options.bookFolder);
  if (!fs.existsSync(inputDir)) {
    throw new Error(`Input directory not found: ${inputDir}`);
  }

  return fs
    .readdirSync(inputDir)
    .map((fileName) => {
      const match = fileName.match(chapterFilePattern);
      if (!match || match[2] !== options.source) {
        return null;
      }

      const chapter = Number.parseInt(match[1], 10);
      if (options.chapter && chapter !== options.chapter) {
        return null;
      }

      return {
        chapter,
        source: match[2],
        path: path.join(inputDir, fileName),
      };
    })
    .filter(Boolean)
    .sort((left, right) => left.chapter - right.chapter);
}

function parseChapterMarkdown(filePath, versePrefix) {
  const verses = [];
  const text = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }

    const match = line.match(verseLinePattern);
    if (!match) {
      throw new Error(`Unable to parse verse line in ${filePath}: ${line}`);
    }

    const verseNumber = Number.parseInt(match[1], 10);
    const verseText = match[2].trim();
    verses.push({
      verse_number: verseNumber,
      verse_text: verseText,
      spoken_line: `${versePrefix} ${verseNumber}. ${verseText}`,
    });
  }

  if (verses.length === 0) {
    throw new Error(`No verse lines found in ${filePath}`);
  }

  return verses;
}

function chunkSpokenLines(verses, maxCharacters) {
  const chunks = [];
  let currentLines = [];
  let currentLength = 0;

  for (const verse of verses) {
    const line = verse.spoken_line;
    const separatorLength = currentLines.length === 0 ? 0 : 2;

    if (currentLines.length > 0 && currentLength + separatorLength + line.length > maxCharacters) {
      chunks.push(currentLines.join("\n\n"));
      currentLines = [];
      currentLength = 0;
    }

    currentLines.push(line);
    currentLength += separatorLength + line.length;
  }

  if (currentLines.length > 0) {
    chunks.push(currentLines.join("\n\n"));
  }

  return chunks;
}

async function requestOpenAiSpeech({ apiKey, input, instructions }) {
  const response = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify({
      model: openAiModel,
      voice: openAiVoice,
      input,
      instructions,
      response_format: "mp3",
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`OpenAI speech request failed (${response.status}): ${errorBody}`);
  }

  return Buffer.from(await response.arrayBuffer());
}

function writeMetadata({ chapterFile, outputPath, metadataPath, verses, chunkCount }) {
  const metadata = {
    source_markdown: path.resolve(chapterFile.path),
    engine: "openai",
    voice: openAiVoice,
    model: openAiModel,
    speak_verse_numbers: true,
    generated_at: new Date().toISOString(),
    tone_profile: toneProfile,
    verse_count: verses.length,
    chunk_count: chunkCount,
    output_audio: path.resolve(outputPath),
  };

  fs.writeFileSync(metadataPath, `${JSON.stringify(metadata, null, 4)}\n`, "utf8");
}

async function generateChapter({ apiKey, options, config, chapterFile }) {
  const outputDir = path.join(repoRoot, "audio", options.language, options.bookFolder);
  fs.mkdirSync(outputDir, { recursive: true });

  const outputPath = path.join(
    outputDir,
    `CHAPTER_${chapterFile.chapter}.from_${chapterFile.source}.mp3`,
  );
  const metadataPath = path.join(
    outputDir,
    `CHAPTER_${chapterFile.chapter}.from_${chapterFile.source}.meta.json`,
  );

  if (
    !options.overwrite &&
    fs.existsSync(outputPath) &&
    fs.existsSync(metadataPath)
  ) {
    console.log(`Skipping existing ${outputPath}`);
    return;
  }

  const verses = parseChapterMarkdown(chapterFile.path, config.versePrefix);
  const chunks = chunkSpokenLines(verses, options.maxChunkCharacters);
  const tempPath = `${outputPath}.tmp`;
  const audioBuffers = [];

  for (let index = 0; index < chunks.length; index += 1) {
    console.log(
      `Requesting chapter ${chapterFile.chapter}, chunk ${index + 1}/${chunks.length}`,
    );
    audioBuffers.push(
      await requestOpenAiSpeech({
        apiKey,
        input: chunks[index],
        instructions: config.instructions,
      }),
    );
  }

  fs.writeFileSync(tempPath, Buffer.concat(audioBuffers));
  fs.renameSync(tempPath, outputPath);
  writeMetadata({
    chapterFile,
    outputPath,
    metadataPath,
    verses,
    chunkCount: chunks.length,
  });
  console.log(`Generated ${outputPath}`);
}

async function main() {
  const options = parseArgs(process.argv);
  const config = languageConfig[options.language];
  if (!config) {
    throw new Error(`Unsupported language: ${options.language}`);
  }

  const apiKey = getOpenAiApiKey();
  if (!apiKey) {
    throw new Error(
      "OPENAI_API_KEY is required. Set it in the environment, .env, or secrets.yaml.",
    );
  }

  const chapterFiles = findChapterFiles(options);
  if (chapterFiles.length === 0) {
    throw new Error("No matching chapter files found.");
  }

  for (const chapterFile of chapterFiles) {
    await generateChapter({ apiKey, options, config, chapterFile });
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
