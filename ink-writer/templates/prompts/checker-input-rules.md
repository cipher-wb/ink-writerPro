<!-- version: 1.0.0 | changelog: initial extraction from 12 checker agent specs -->

## 输入硬规则

- 必须先读取 `review_bundle_file`。
- 若 `review_bundle_file` 缺失，直接返回 `pass=false`，并说明 `REVIEW_BUNDLE_MISSING`；禁止自行扫描项目目录补救。
- 默认只使用审查包内嵌的数据（正文、上下文、快照等）。
- 仅当审查包明确缺字段时，才允许补充读取 `allowed_read_files` 中列出的**绝对路径**文件。
- **禁止读取** `.db` 文件、目录路径、以及白名单外的相对路径。
