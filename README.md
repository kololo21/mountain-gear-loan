# 山岳部 備品貸出管理 (Mountain Club Gear Loan Manager)

山岳部の備品・部員・山行・貸出を管理する Web アプリ。データモデリング講義の最終課題として、AI の支援を受けながら作成した。

- Python + Flask + SQLite3(ORM は使わず、すべて SQL 文で操作)
- テーブル: `members` / `equipment` / `trips` / `loans`(+ 2 ビュー)
- `database.db` にはダミーのサンプルデータが入っている

`get_db` / `close_connection` は [trueroad/dm_app](https://github.com/trueroad/dm_app) のサンプルアプリを流用している。

## 実行

```
pip install flask
flask --app app run
```

`index.cgi` は大学のサーバ(CGI)に設置するためのもの。
