from __future__ import annotations

import unittest

import code_parser


VUE_SAMPLE = """<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const drawerDoc = ref(null)
const open = ref(false)

const title = computed(() => `${drawerDoc.value?.name || ''} 预览`)

async function openDocument(id) {
  open.value = true
  drawerDoc.value = await api.getDocument(id)
}

watch(
  () => props.documentId,
  (id) => {
    if (id) openDocument(id)
  },
)

onMounted(() => {
  emit('ready')
})
</script>

<template>
  <button @click="openDocument(id)">打开</button>
</template>
"""


class CodeParserTests(unittest.TestCase):
    def test_vue_symbols_and_lines(self) -> None:
        parsed = code_parser.parse_code("DocumentDrawer.vue", VUE_SAMPLE)
        names = {item["name"]: item for item in parsed["symbols"]}
        self.assertIn("drawerDoc", names)
        self.assertEqual(names["drawerDoc"]["kind"], "state")
        self.assertIn("title", names)
        self.assertEqual(names["title"]["kind"], "computed")
        functions = {
            item["name"]: item
            for item in parsed["symbols"]
            if item["kind"] == "function"
        }
        self.assertIn("openDocument", functions)
        self.assertEqual(functions["openDocument"]["kind"], "function")
        self.assertIn("onMounted", names)
        self.assertTrue(any(item["kind"] == "api" and item["name"] == "api.getDocument" for item in parsed["symbols"]))

    def test_function_end_line_covers_body(self) -> None:
        parsed = code_parser.parse_code("DocumentDrawer.vue", VUE_SAMPLE)
        function = next(item for item in parsed["symbols"] if item["name"] == "openDocument")
        self.assertGreaterEqual(function["end_line"], function["line"] + 2)
        lines = code_parser.get_lines(VUE_SAMPLE)
        covered = "\n".join(lines[function["line"] - 1 : function["end_line"]])
        self.assertIn("drawerDoc.value = await api.getDocument(id)", covered)

    def test_template_binding(self) -> None:
        parsed = code_parser.parse_code("DocumentDrawer.vue", VUE_SAMPLE)
        self.assertTrue(any(item["name"] == "openDocument" and item["kind"] == "binding" for item in parsed["symbols"]))

    def test_plain_ts(self) -> None:
        parsed = code_parser.parse_code("utils.ts", "export function pad(n: number) {\n  return String(n).padStart(2, '0')\n}\n")
        self.assertEqual(parsed["language"], "typescript")
        self.assertIn("pad", parsed["symbol_names"])

    def test_empty_raises(self) -> None:
        with self.assertRaises(code_parser.CodeParseError):
            code_parser.parse_code("x.js", "   ")

    def test_unsupported_extension(self) -> None:
        with self.assertRaises(code_parser.CodeParseError):
            code_parser.parse_code("x.py", "print('hi')")


if __name__ == "__main__":
    unittest.main()
