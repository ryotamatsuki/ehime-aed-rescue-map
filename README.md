# えひめAEDレスキューマップ — Precision Model v2

**AEDの場所を探す地図ではなく、AEDが届きにくい人口を100m単位で探し、「次の1台」を道路距離で考える地図。**

松山市のAED・公共施設オープンデータ、令和2年簡易100mメッシュ人口、OpenStreetMap歩行ネットワークを組み合わせる静的WebGIS PoCです。

公開URL: https://ryotamatsuki.github.io/ehime-aed-rescue-map/

## v2で変わったこと

初版の「44地域人口を公共施設位置へ均等配分」「直線距離」を廃止し、次のモデルへ置き換えます。

- 需要点: 2020年国勢調査250m人口を建物面積等で按分した **簡易100mメッシュ人口**
- 高齢者: 同データの `Pop75over` を直接使用
- 距離: **OpenStreetMap歩行ネットワーク最短経路距離**
- 距離には100mメッシュ中心→道路、AED/候補→道路のsnap距離も含める
- 「次の1台」も公共施設候補→未カバー100mメッシュの道路最短距離で評価
- 24時間利用可AEDモードも同じネットワークで別途multi-source shortest pathを計算

## データ

| データ | 用途 | 時点 | ライセンス |
|---|---|---|---|
| 松山市 AED設置箇所一覧 | AED位置・利用可能日時 | 2025-03-01 | CC BY |
| 令和2年簡易100mメッシュ人口（松山市） | 総人口・65+・75+・85+ | 2020 Census based | CC BY |
| 松山市 公共施設一覧 | 新規AED配置候補 | 2024-02-20 | CC BY |
| OpenStreetMap | 歩行ネットワーク | build時点 | ODbL 1.0 |

### 100m人口について

`https://gtfs-gis.jp/teikyo/` で公開される「令和2年簡易100mメッシュ人口」を利用します。これは令和2年国勢調査の250mメッシュ人口を、50mメッシュ建物面積・土地利用等を用いて100mへ按分した**推計値**です。100mセルで実測・集計された国勢調査人口ではありません。

本アプリでは2020年100m分布を2026年人口へ機械的に按分・上書きしません。空間分布の精度とデータ時点を混同しないためです。

直接取得URL:

`https://gtfs-gis.jp/data/100m_pop2020/38/100m_mesh_pop2020_38201.zip`

## 歩行距離モデル

`python scripts/update_data.py` が次を実行します。

1. AED、簡易100m人口、公共施設を原典から取得
2. 人口/AEDが存在する0.1度タイルを抽出し、周囲0.015度をbuffer
3. Overpass APIから `highway=*` を取得
4. `motorway` / `motorway_link` / `construction` / `proposed` / `raceway`、`foot=no`、`access=no/private`、`area=yes` を歩行グラフから除外
5. 残るwayを歩行グラフ化
6. 100m人口中心は300m以内、AEDは200m以内、候補公共施設は200m以内の道路ノードへsnap
7. AED→全道路ノードのmulti-source Dijkstraを実行
8. `mesh snap + road shortest path + AED snap` を最短歩行距離とする
9. 候補ごとに640mで打ち切るDijkstraを行い、到達可能な100mメッシュだけを保存

歩行グラフは歩行者について双方向として扱います。`foot=no` 等の明示禁止は除外しますが、階段負荷、勾配、信号待ち、横断待ち、建物内部移動、実際の入口位置はまだモデル化していません。

## 「4分圏」

デフォルトは **320m** です。歩行速度4.8km/h（80m/分）で**片道4分相当**という分析設定です。医学的救命基準やAED取得往復4分を意味しません。UIでは80〜640mを20m刻みで変更できます。

## 配置最適化

配置候補は松山市公共施設です。既存AEDと直線またはネットワーク距離で50m未満の候補は除外します。

ある半径 `r` について、既存AEDでは未カバーかつ候補からの歩行ネットワーク距離が `r` 以下の100mメッシュ人口を合計し、その増分が最大の候補を「次の1台」とします。同点時は75歳以上の追加カバー人口を優先します。

これは施設設置の最終判断ではなく、**配置候補のスクリーニング**です。所有者同意、営業時間、電源・温度管理、費用、救急需要、昼間人口等は別途必要です。

## データ品質上の扱い

- 道路へsnapできない100m人口は削除せず、未カバー人口の分母に残す
- 道路へsnapできないAEDは地図には残せるが、ネットワークカバレッジ計算から除外
- OSM取得は複数タイル＋2つのOverpass endpointへのretryを実装
- UI上の円形バッファは廃止。道路距離モデルなのに直線円を描く誤解を防ぐため
- 地図描画は端末負荷対策として未カバー100mメッシュのうち人口上位最大5,000点。KPI計算は全メッシュを使用

## ローカル実行

```bash
python scripts/update_data.py
python -m unittest discover -s tests -v
python scripts/qa.py
python -m http.server 8000
```

`http://localhost:8000/` を開きます。

生成される `data/raw/` と `data/processed.json` はGit管理対象外です。

## CI / Pages

Pull Request / push CIは毎回、公開原典からデータとOSM歩行ネットワークを取得し直して以下を検査します。

- 100m mesh schema / meshcode conversion
- OSM graph生成
- AED / population mesh snap
- 24h AED subset
- network shortest path
- candidate reach pairs
- unsnapped population share
- default 320m all/24h analysis
- JavaScript syntax

CIは `processed.json` とQAログをartifactとして保存します。mainのPages workflowも同じQAを通過したものだけを公開します。

## ライセンス

アプリコード: MIT License。

各データの著作権・ライセンスは各提供者に帰属します。OpenStreetMapデータは © OpenStreetMap contributors / ODbL 1.0 です。
