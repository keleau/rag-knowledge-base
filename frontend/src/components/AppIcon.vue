<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

const paths: Record<string, string[]> = {
  plus: ['M12 5v14', 'M5 12h14'],
  send: ['M22 2 11 13', 'M22 2 15 22 11 13 2 9 22 2'],
  stop: ['M7 7h10v10H7z'],
  trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13', 'M10 11v5', 'M14 11v5'],
  doc: [
    'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z',
    'M14 3v5h5',
    'M9 13h6',
    'M9 17h4',
  ],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  chevron: ['M6 9l6 6 6-6'],
  edit: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z'],
  upload: ['M12 16V4', 'M7 9l5-5 5 5', 'M4 20h16'],
  download: ['M12 4v12', 'M7 11l5 5 5-5', 'M4 20h16'],
  spark: [
    'M12 2v4',
    'M12 18v4',
    'M2 12h4',
    'M18 12h4',
    'M4.9 4.9l2.8 2.8',
    'M16.3 16.3l2.8 2.8',
    'M4.9 19.1l2.8-2.8',
    'M16.3 7.7l2.8-2.8',
  ],
  menu: ['M4 7h16', 'M4 12h16', 'M4 17h16'],
  library: [
    'M4 19.5A2.5 2.5 0 0 1 6.5 17H20',
    'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z',
  ],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'M21 21l-4.35-4.35'],
  check: ['M20 6 9 17l-5-5'],
  info: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 16v-5', 'M12 8h.01'],
  alert: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 8v5', 'M12 17h.01'],
  copy: ['M8 8h12v12H8z', 'M16 8V4H4v12h4'],
  eye: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
  arrow: ['M5 12h14', 'M13 6l6 6-6 6'],
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(path, index) in paths[name] || []" :key="index" :d="path" />
  </svg>
</template>
