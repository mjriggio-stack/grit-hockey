# rebuild_all_seasons_v31.ps1
#
# Rebuilds all 19 GRIT seasons (10 RS + 9 PO) under v3.1.
# Fail-fast: stops on first error.
# Writes to real output dirs (data\{tag}\) — overwrites v3 production.
# SQL grit_scores rows for each season/playoff are overwritten by build_v3.py
# (DELETE WHERE runs before insert).
#
# Run from: C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\source
# Wall time: ~2-4 minutes per season on this hardware.
#
# Tag convention follows build_v3.py: end-year (2023 = 2022-23 season).
# COVID bubble (2020-21, tag 2021) intentionally excluded.

$ErrorActionPreference = "Stop"

# Cache roots (per project memory + 2026-05-08 confirmation)
$GritCache = "C:\Users\mjrig\OneDrive\Documents\Grit\cache"
$V3Cache   = "C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\cache"
$DataRoot  = "C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data"

# Season layout: tag -> RS cache root, PO cache root (or $null if PO skipped)
# 2019-20 (tag 2020): RS exists, no PO under v3 per FAQ
# 2020-21 (tag 2021): excluded entirely (COVID bubble)
$Seasons = @(
    @{ Tag = 2016; RsRoot = $GritCache; PoRoot = $GritCache },
    @{ Tag = 2017; RsRoot = $GritCache; PoRoot = $GritCache },
    @{ Tag = 2018; RsRoot = $GritCache; PoRoot = $GritCache },
    @{ Tag = 2019; RsRoot = $GritCache; PoRoot = $GritCache },
    @{ Tag = 2020; RsRoot = $GritCache; PoRoot = $null      },  # 2019-20: RS only (no PO cache)
    @{ Tag = 2022; RsRoot = $GritCache; PoRoot = $GritCache },  # tag 2021 = COVID, skipped
    @{ Tag = 2023; RsRoot = $V3Cache;   PoRoot = $V3Cache   },
    @{ Tag = 2024; RsRoot = $V3Cache;   PoRoot = $V3Cache   },
    @{ Tag = 2025; RsRoot = $V3Cache;   PoRoot = $V3Cache   },
    @{ Tag = 2026; RsRoot = $GritCache; PoRoot = $GritCache }
)

function Build-Season {
    param(
        [int]$Tag,
        [string]$CacheRoot,
        [bool]$IsPlayoffs
    )

    $tagStr   = if ($IsPlayoffs) { "${Tag}_playoffs" } else { "$Tag" }
    $label    = if ($IsPlayoffs) { "$Tag PO" } else { "$Tag RS" }
    $cacheDir = Join-Path $CacheRoot $tagStr
    $pbpDir   = Join-Path $cacheDir "pbp"
    $toiPath  = Join-Path $cacheDir "toi_${tagStr}.csv"
    $outDir   = Join-Path $DataRoot $tagStr

    Write-Host ""
    Write-Host "===== Building $label =====" -ForegroundColor Cyan
    Write-Host "  PBP cache : $pbpDir"
    Write-Host "  TOI       : $toiPath"
    Write-Host "  Output    : $outDir"

    if (-not (Test-Path $pbpDir)) {
        throw "PBP cache directory not found: $pbpDir"
    }
    if (-not (Test-Path $toiPath)) {
        throw "TOI file not found: $toiPath"
    }

    $args = @(
        "build_v3.py",
        "--pbp-cache",   $pbpDir,
        "--toi",         $toiPath,
        "--output-dir",  $outDir,
        "--season-tag",  $tagStr
    )
    if ($IsPlayoffs) { $args += "--playoffs" }

    $start = Get-Date
    & python @args
    if ($LASTEXITCODE -ne 0) {
        throw "build_v3.py failed for $label (exit $LASTEXITCODE)"
    }
    $elapsed = (Get-Date) - $start
    Write-Host ("  Done in {0:N1}s" -f $elapsed.TotalSeconds) -ForegroundColor Green
}

# Run
$totalStart = Get-Date
$rsCount = 0
$poCount = 0

foreach ($s in $Seasons) {
    Build-Season -Tag $s.Tag -CacheRoot $s.RsRoot -IsPlayoffs $false
    $rsCount++

    if ($null -ne $s.PoRoot) {
        Build-Season -Tag $s.Tag -CacheRoot $s.PoRoot -IsPlayoffs $true
        $poCount++
    }
}

$totalElapsed = (Get-Date) - $totalStart
Write-Host ""
Write-Host "===== ALL DONE =====" -ForegroundColor Green
Write-Host "  $rsCount RS + $poCount PO = $($rsCount + $poCount) builds"
Write-Host ("  Total wall time: {0:N1} min" -f $totalElapsed.TotalMinutes)
