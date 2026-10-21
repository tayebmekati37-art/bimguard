# BIMGuard - BIM 変更影響・情報整合性エンジン

バージョン管理は「何が変わったか」を教えてくれます。
BIMGuard は「その変更が何に影響するか」を教えてくれます。

BIM プロジェクト向けの決定論的エンジンです。リビジョン間の変更を検出し、型付き依存関係をたどり、影響度をスコア化し、検証ルールを実行して発行可否を判定します。オプションの AI レイヤーは事実を言い換えるだけで、判断は一切行いません。

**バージョン:** 1.0.0

> **注:** 本 README の日本語訳は現在準備中です。詳細は英語版 `README.md` を参照してください。以下は概要のみです。完全な機能一覧、セットアップ手順、テスト方法は英語版に記載されています。

## 主な機能

- IFC または JSON 形式のモデルリビジョンをアップロード
- リビジョン間の変更を検出
- 文書間の型付き依存関係グラフを構築
- 変更の影響を到達可能な全文書に対してスコア化
- 検証ルールを実行し、READY / READY_WITH_WARNINGS / BLOCKED を判定
- 文書ごとの健全性(正常・注意・要確認・重大)と理由を算出
- 任意で AI による言い換え(グラウンディングチェック付き)
- 発行可否レポートを JSON・CSV・PDF で出力
- 影響ユーザーへの通知、すべての操作を監査ログに記録

## 起動方法

Docker の場合:

    Copy-Item .env.example .env
    docker compose up --build

ネイティブ(Windows・PowerShell)の場合:

    cd apps\api
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -m app.seed
    uvicorn app.main:app --reload

別ターミナルで:

    cd apps\web
    npm install
    npm run dev

## テスト

バックエンド:

    cd apps\api
    .\.venv\Scripts\python.exe -m pytest -q

E2E(Playwright、ローカルでは headed):

    cd C:\dev\bimguard
    powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1

## デモの検証

決定論的パイプラインが期待どおりに動作するか確認します:

    powershell -ExecutionPolicy Bypass -File scripts\verify-demo.ps1

## ドキュメント

- `docs/architecture/ai.md` - AI 説明レイヤー
- `docs/architecture/reports.md` - 発行可否レポート
- `docs/architecture/profiles.md` - 品質プロファイル
- `docs/architecture/interoperability.md` - JSON エクスポートと検証
- `docs/architecture/manufacturing.md` - 製造業ドメイン
- `docs/architecture/deployment.md` - デプロイ、バックアップ、セキュリティ範囲
- `docs/architecture/i18n.md` - 英語・日本語対応
- `docs/evaluation/demo-dataset.md` - デモデータセットの期待結果
- `docs/evaluation/metrics.md` - 計測方法と制約

## 既知の制約

- 完全な日本語 UI 対応は未完了です(ヘッダーナビゲーションのみ対応)
- ジオメトリの完全比較(2D 図面と 3D モデルの照合)は未実装です
- BCF 形式の入出力は未実装です
- IFC の書き出しは未実装です
- トークンの失効機能はありません(有効期限まで有効)
- 保存データの暗号化は行っていません

詳細は `docs/architecture/deployment.md` の「What this milestone does NOT ship」を参照してください。