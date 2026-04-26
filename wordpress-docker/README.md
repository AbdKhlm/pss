# dockerize-wordpress

# Langkah - Langkah Menjalankan Stack (WordPress + MySQL + Redis)

## 1. Siapkan Project

### mkdir wordpress-docker
### cd wordpress-docker


## 2. Buat file docker-compose.yml

### New-Item docker-compose.yml
#### Isi dengan konfigurasi yang telah disiapkan


## 3. Jalankan Docker Compose

### docker-compose up -d
#### artinya :
#### up -> menjalankan semua service
#### -d -> jalan di background


## 4. Cek apakah semua container berjalan

### docker ps
#### Pastikan ada 3 container:
#### 1.WordPress
#### 2.MySQL
#### 3.Redis


## 5. Akses WordPress

### Buka browser:
### http://localhost:8000
#### Akan muncul halaman instalasi WordPress


## 6. Setup WordPress

### Isi:
### - Site Title
### - Username
### - Password
### - Email
### Klik Install WordPress


## 7. Test Website

### - Login ke dashboard
### - Buat Post / Page
### - Pastikan tidak error


## 8. Test Data Persistence

### Stop container:
#### docker-compose down

### Jalankan lagi:
#### docker-compose up -d
#### cek:
#### - jika masih terdapat post maka dinyatakan berhasil


## 9. Test Redis

### Cara cepat:
#### docker exec -it <nama_container_redis> redis-cli ping

### Output:
#### PONG


## 10. Stop Semua Service

### docker-compose down


# Screenshot WordPress installation page

![alt text](https://github.com/AbdKhlm/pss/blob/main/wordpress-docker/public/Install-Webpage.png?raw=true)

# Screenshot WordPress dashboard

![alt text](https://github.com/AbdKhlm/pss/blob/main/wordpress-docker/public/Dashboard.png?raw=true)

# Screenshot docker ps menunjukkan 3 containers running

![alt text](https://github.com/AbdKhlm/pss/blob/main/wordpress-docker/public/docker%20ps.png?raw=true)

# Screenshot Redis CLI ping test

![alt text](https://github.com/AbdKhlm/pss/blob/main/wordpress-docker/public/Redis%20CLI%20ping.png?raw=true)

# Jawaban pertanyaan:

 ## Kenapa perlu volume untuk MySQL?
  ### dikarenakan fungsi volume adalah untuk menyimpan data, data akan hilang jika container dihapus atau volume tidak ditambahkan.

## Apa fungsi depends_on?
 ### depends_on berfungsi menjalankan container secara berurutan.
 ### serta memastikan WordPress berjalan setelah MySQL dan Redis.

## Bagaimana cara WordPress container connect ke MySQL?
 ### dengan menggunakan fungsi:
 #### WORDPRESS_DB_HOST: mysql:3306
 ### mysql adalah nama service -> Docker otomatis jadi hostname.

## Apa keuntungan pakai Redis untuk WordPress?
 ### - MySQL tidak cepat overload
 ### - Lebih stabil saat traffic tinggi
