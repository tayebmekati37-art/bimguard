# はじめに

このガイドでは、クローン直後の状態から 10 分以内に動作するデモまで導きます。

> **翻訳について:** 本ドキュメントは英語版 `docs/en/getting-started.md` の日本語訳です。技術的な内容は英語版と一致していますが、完全な一致を保証するものではありません。相違がある場合は英語版を正とします。

## 前提条件

- Python 3.12 以上
- Node.js 20 以上
- PowerShell(Windows)または POSIX シェル(macOS・Linux)
- Docker(任意。コンテナ版を使う場合のみ)

## ネイティブセットアップ(評価用途ではこちらを推奨)

### ターミナル 1 - API

    cd apps\api
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -m app.seed
    uvicorn app.main:app --reload

API は `http://localhost:8000`、ドキュメントは `http://localhost:8000/docs` で提供されます。

### ターミナル 2 - フロントエンド

    cd apps\web
    npm install
    npm run dev

フロントエンドは `http://localhost:3000` で提供されます。

### ログイン

    admin@example.local / admin-demo-pass

### デモプロジェクトの読み込み

    powershell -ExecutionPolicy Bypass -File scripts\load-sample-project.ps1 -WithArchitectureV2

5 つの文書と 5 つの依存関係を持つプロジェクトが作成され、A-101 v13 がアップロードされます。この時点のプロジェクトは `docs/evaluation/demo-dataset.md` に記載の状態になっているはずです。

## Docker

    Copy-Item .env.example .env
    docker compose up --build

バックエンドは `:8000`、Postgres は `:5432` で起動します。このマイルストーンでは Web アプリはコンテナ化されていません。`apps/web` で `npm run dev` を実行し、コンテナの API に接続してください。

## デモの検証

    powershell -ExecutionPolicy Bypass -File scripts\verify-demo.ps1

デモのコピーを新規に読み込み、A-101 v13 をアップロードしたうえで、デモ文書が約束する健全性状態・依存関係の陳腐化・検証結果を検証します。1 つでも不一致があれば非ゼロで終了します。

## テストの実行

    cd apps\api
    .\.venv\Scripts\python.exe -m pytest -q

期待結果:約 353 件成功、8 件スキップ。

E2E:

    powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1

期待結果:12 件のテストが Chrome ウィンドウで実行され成功。

## 性能の計測

    powershell -ExecutionPolicy Bypass -File scripts\benchmark.ps1

検証を 5 回実行し、p50・p95・最小・最大を報告します。全実行が同一の検出結果を生むことも確認します。観測値を報告するのみで、業界ベンチマークを主張するものではありません。

## 次のステップ

- `docs/evaluation/demo-dataset.md` - デモが出力すべき内容
- `docs/evaluation/metrics.md` - 計測方法と制約
- `docs/architecture/` - 各サブシステムの設計メモ