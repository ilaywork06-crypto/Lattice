import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n } from './i18n'
import { vuetify } from './plugins/vuetify'
import { installAuthInterceptor } from './stores/auth'
import './styles/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n) // must precede vuetify (its locale adapter consumes vue-i18n)
app.use(vuetify)

// Register the axios 401 → logout handler now that Pinia exists.
installAuthInterceptor()

app.mount('#app')
