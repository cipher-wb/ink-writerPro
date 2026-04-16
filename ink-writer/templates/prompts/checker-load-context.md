<!-- version: 1.0.0 | changelog: initial extraction from 3 checker agent specs -->

### 第一步: 加载上下文

**输入参数**:
```json
{
  "project_root": "{PROJECT_ROOT}",
  "chapter_file": "{ABSOLUTE_CHAPTER_FILE}",
  "review_bundle_file": "{ABSOLUTE_REVIEW_BUNDLE_FILE}"
}
```

先读取 `review_bundle_file`。只有当审查包没有给出必要字段时，才允许补读 `allowed_read_files` 中的绝对路径文件。
