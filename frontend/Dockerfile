# Этап 1: Сборка
FROM node:18-alpine AS build 

WORKDIR /app

# Сначала копируем только файлы зависимостей. 
# Это позволит Docker кешировать 'npm install' и не переустанавливать пакеты при каждом изменении кода.
COPY package*.json ./
RUN npm install

# Теперь копируем остальной код и собираем
COPY . .
RUN npm run build

# Этап 2: Раздача через Nginx
FROM nginx:alpine

# Очищаем дефолтные файлы (хорошая практика)
RUN rm -rf /usr/share/nginx/html/*

# Копируем билд из первого этапа
# Важно: проверь, что твоя сборка (Vite/React) создает именно папку 'dist'.
# Если это старый Create React App, то папка будет называться 'build'.
COPY --from=build /app/dist /usr/share/nginx/html

# Пробрасываем порт
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]