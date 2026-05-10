param(
    [string[]]$Languages = @("bho", "ptb")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FfmpegPath = "ffmpeg"

# Keep the OpenAI configuration easy to retune without touching the parsing logic.
$OpenAiModel = "gpt-4o-mini-tts"
$OpenAiVoice = "onyx"
$BhoOpenAiToneInstructions = "Narrate scripture with a male voice and a serious, reverent tone. Keep the delivery lower, fuller, and steady, with a subtle groove rather than a bright conversational feel. Read Devanagari naturally and keep each verse number clearly audible."
$PtbOpenAiToneInstructions = "Narrate scripture in Brazilian Portuguese with a male voice and a serious, reverent tone. Keep the delivery lower, fuller, and steady, with a subtle groove rather than a bright conversational feel. Read each verse number clearly."

function Get-OpenAiApiKeyFromSecretsFile {
    $candidatePaths = @(
        (Join-Path $RepoRoot "secrets.yaml"),
        (Join-Path $PSScriptRoot "secrets.yaml")
    )

    foreach ($candidatePath in $candidatePaths) {
        if (-not (Test-Path -LiteralPath $candidatePath)) {
            continue
        }

        $secretText = Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8
        $patterns = @(
            'OPENAI_API_KEY\s*[:=]\s*"([^"]+)"',
            "OPENAI_API_KEY\s*[:=]\s*'([^']+)'",
            'OPENAI_API_KEY\s*[:=]\s*([^\r\n#]+)'
        )

        foreach ($pattern in $patterns) {
            $match = [regex]::Match($secretText, $pattern)
            if ($match.Success) {
                return $match.Groups[1].Value.Trim()
            }
        }
    }

    return $null
}

function Get-OpenAiApiKey {
    $processValue = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
    if ($processValue) {
        return $processValue
    }

    $userValue = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
    if ($userValue) {
        return $userValue
    }

    $machineValue = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Machine")
    if ($machineValue) {
        return $machineValue
    }

    $secretsFileValue = Get-OpenAiApiKeyFromSecretsFile
    if ($secretsFileValue) {
        return $secretsFileValue
    }

    return $null
}

function Get-TargetDefinitions {
    return @(
        [ordered]@{
            language            = "bho"
            book_folder         = "01_GEN"
            chapter             = 1
            source              = "wtm"
            input_path          = Join-Path $RepoRoot "text\bho\01_GEN\CHAPTER_1.from_wtm.md"
            output_dir          = Join-Path $RepoRoot "audio\bho\01_GEN"
            verse_prefix        = "पद"
            engine              = "openai"
            voice               = $OpenAiVoice
            model               = $OpenAiModel
            tone_profile        = "male, serious, reverent, lower, fuller, subtle groove"
            openai_instructions = $BhoOpenAiToneInstructions
        }
        [ordered]@{
            language            = "ptb"
            book_folder         = "01_GEN"
            chapter             = 1
            source              = "wtm"
            input_path          = Join-Path $RepoRoot "text\ptb\01_GEN\CHAPTER_1.from_wtm.md"
            output_dir          = Join-Path $RepoRoot "audio\ptb\01_GEN"
            verse_prefix        = "Versículo"
            engine              = "openai"
            voice               = $OpenAiVoice
            model               = $OpenAiModel
            tone_profile        = "male, serious, reverent, lower, fuller, subtle groove"
            openai_instructions = $PtbOpenAiToneInstructions
        }
    )
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Parse-ChapterMarkdown {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$VersePrefix
    )

    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $lines = $raw -split "`r?`n" | Where-Object { $_.Trim() }
    $verses = @()

    foreach ($line in $lines) {
        if ($line -notmatch '^\*\*(\d+)\*\*\s+(.+)$') {
            throw "Unable to parse verse line in '$Path': $line"
        }

        $verseNumber = [int]$Matches[1]
        $verseText = $Matches[2].Trim()
        $spokenLine = "{0} {1}. {2}" -f $VersePrefix, $verseNumber, $verseText

        $verses += [pscustomobject]@{
            verse_number = $verseNumber
            verse_text   = $verseText
            spoken_line  = $spokenLine
        }
    }

    return $verses
}

function Join-SpokenVerses {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Verses
    )

    return ($Verses | ForEach-Object { $_.spoken_line }) -join "`r`n`r`n"
}

function New-TempFilePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Extension
    )

    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("bible-audio-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    return Join-Path $tempDir ("audio" + $Extension)
}

function Remove-TempArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $parent = Split-Path -Parent $Path
    if ($parent -and (Test-Path -LiteralPath $parent)) {
        Remove-Item -LiteralPath $parent -Recurse -Force
    }
}

function Invoke-OpenAiSpeechToWave {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$ApiKey,

        [Parameter(Mandatory = $true)]
        [string]$Model,

        [Parameter(Mandatory = $true)]
        [string]$Voice,

        [Parameter(Mandatory = $true)]
        [string]$Instructions,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $payload = [ordered]@{
        model           = $Model
        voice           = $Voice
        input           = $Text
        instructions    = $Instructions
        response_format = "wav"
    } | ConvertTo-Json -Depth 5

    Invoke-WebRequest `
        -Method Post `
        -Uri "https://api.openai.com/v1/audio/speech" `
        -Headers @{ Authorization = "Bearer $ApiKey" } `
        -ContentType "application/json; charset=utf-8" `
        -Body $payload `
        -OutFile $OutputPath | Out-Null
}

function Convert-WaveToNormalizedMp3 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputPath,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $ffmpegArgs = @(
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", $InputPath,
        "-ac", "1",
        "-ar", "24000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-b:a", "64k",
        $OutputPath
    )

    & $FfmpegPath @ffmpegArgs
    if ($LASTEXITCODE -ne 0) {
        throw "ffmpeg failed while generating '$OutputPath'."
    }
}

function Write-MetadataFile {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Target,

        [Parameter(Mandatory = $true)]
        [object[]]$Verses,

        [Parameter(Mandatory = $true)]
        [string]$AudioPath,

        [Parameter(Mandatory = $true)]
        [string]$MetadataPath
    )

    $metadata = [ordered]@{
        source_markdown      = (Resolve-Path -LiteralPath $Target.input_path).Path
        engine               = $Target.engine
        voice                = $Target.voice
        model                = $Target.model
        speak_verse_numbers  = $true
        generated_at         = (Get-Date).ToString("o")
        tone_profile         = $Target.tone_profile
        verse_count          = $Verses.Count
        output_audio         = $AudioPath
    }

    $metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $MetadataPath -Encoding UTF8
}

$targets = Get-TargetDefinitions
$selectedLanguages = $Languages | ForEach-Object { $_.ToLowerInvariant() }
$unknownLanguages = $selectedLanguages | Where-Object { $_ -notin $targets.language }
if ($unknownLanguages) {
    throw "Unsupported language selection: $($unknownLanguages -join ', '). Supported values: $($targets.language -join ', ')"
}

$selectedTargets = $targets | Where-Object { $_.language -in $selectedLanguages }
if (-not $selectedTargets) {
    throw "No chapter targets selected."
}

$openAiApiKey = Get-OpenAiApiKey
if (-not $openAiApiKey) {
    throw "OPENAI_API_KEY is required for cloud generation. Set it in the process, user, or machine environment, or store it in secrets.yaml."
}

foreach ($target in $selectedTargets) {
    if (-not (Test-Path -LiteralPath $target.input_path)) {
        throw "Input chapter file not found: $($target.input_path)"
    }

    Ensure-Directory -Path $target.output_dir

    $verses = Parse-ChapterMarkdown -Path $target.input_path -VersePrefix $target.verse_prefix
    if ($verses.Count -ne 31) {
        throw "Expected 31 verses in '$($target.input_path)', found $($verses.Count)."
    }

    $spokenText = Join-SpokenVerses -Verses $verses
    $tempWavePath = New-TempFilePath -Extension ".wav"
    $finalAudioPath = Join-Path $target.output_dir ("CHAPTER_{0}.from_{1}.mp3" -f $target.chapter, $target.source)
    $metadataPath = Join-Path $target.output_dir ("CHAPTER_{0}.from_{1}.meta.json" -f $target.chapter, $target.source)

    try {
        Invoke-OpenAiSpeechToWave `
            -Text $spokenText `
            -ApiKey $openAiApiKey `
            -Model $target.model `
            -Voice $target.voice `
            -Instructions $target.openai_instructions `
            -OutputPath $tempWavePath

        Convert-WaveToNormalizedMp3 -InputPath $tempWavePath -OutputPath $finalAudioPath
        Write-MetadataFile -Target $target -Verses $verses -AudioPath $finalAudioPath -MetadataPath $metadataPath
        Write-Host ("Generated {0}" -f $finalAudioPath)
    }
    finally {
        Remove-TempArtifacts -Path $tempWavePath
    }
}
