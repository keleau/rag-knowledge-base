# 本次改造的验证状态

实现已完成，但当前会话环境里 Bash 工具不可用（执行任何命令都会失败），因此：
- 单元测试没有在这里跑过；
- `npm run build`（vue-tsc 类型检查）没有跑过；
- 服务没有启动过。

请在本地按 README 的「项目定向测评」章节执行：

```bash
cd backend
LLM_MODE=demo .venv/Scripts/python.exe -m unittest discover -s tests -v
```

```bash
cd backend
LLM_MODE=demo .venv/Scripts/python.exe scripts/smoke_assessment.py
```

```bash
cd backend
LLM_MODE=demo .venv/Scripts/python.exe scripts/e2e_fake_llm.py
```

```bash
cd frontend
npm run build
```

有任何报错，把输出贴回来即可继续修。
