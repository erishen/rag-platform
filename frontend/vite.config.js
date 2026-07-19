import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期用 Vite 代理把 /api 转发到后端 FastAPI（:8000），
// 这样浏览器同源访问 /api/*，规避 CORS。生产构建产物若独立托管，
// 后端已开启 CORSMiddleware，可直接跨域访问 :8000。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
