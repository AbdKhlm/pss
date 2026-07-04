# Cache Report

## Ringkasan

Tugas Chapter 11 diimplementasikan menggunakan Redis untuk menyimpan hasil `get_weather(city)` selama 5 menit (`300` detik). Dengan pendekatan ini, pemanggilan pertama tetap lambat karena masih melakukan simulasi API call, sedangkan pemanggilan kedua jauh lebih cepat karena data diambil langsung dari Redis.

## File yang Ditambahkan

- [code/chapter11/weather_api.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/chapter11/weather_api.py)
- [code/chapter11/test_cache.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/chapter11/test_cache.py)

## Redis yang Digunakan

Redis sudah tersedia di Docker Compose project ini melalui service `redis`.

### Menjalankan Redis

```bash
docker-compose up -d redis
```

### Mengecek Redis

```bash
docker-compose exec redis redis-cli ping
```

Expected output:

```text
PONG
```

## Logika Caching

Implementasi pada `get_weather(city)`:

1. Bentuk cache key berdasarkan nama kota, misalnya `weather:jakarta`
2. Cek Redis terlebih dahulu dengan `GET`
3. Jika data ada di cache:
   - decode JSON
   - kembalikan hasil dari Redis
4. Jika data tidak ada:
   - jalankan simulasi API call lambat (`sleep(2)`)
   - simpan hasil ke Redis dengan `SET`
   - atur masa berlaku key dengan `EXPIRE 300`
   - kembalikan hasil ke caller

## Redis Commands yang Digunakan

- `GET weather:jakarta`
- `SET weather:jakarta "<json-data>"`
- `EXPIRE weather:jakarta 300`

Command tambahan untuk verifikasi:

- `DEL weather:jakarta`
- `TTL weather:jakarta`

## Cara Menjalankan Pengujian

```bash
docker-compose exec web python chapter11/test_cache.py
```

## Hasil Pengujian

Hasil aktual dari environment Docker project ini:

```text
First call: 2.11s
First result cache status: miss
Second call (cached): 0.01s
Second result cache status: hit
Current TTL: 300s
Third call after cache expired (300 detik) akan kembali lambat karena Redis sudah menghapus key dan fungsi harus memanggil API lagi.
```

Perbedaan waktu menunjukkan bahwa cache berhasil mengurangi response time pada pemanggilan berikutnya.

## Kenapa Response Time Berbeda?

Karena pemanggilan pertama masih menjalankan simulasi API call yang lambat selama 2 detik, lalu baru menyimpan hasil ke Redis. Pada pemanggilan kedua, aplikasi tidak perlu memanggil API lagi dan cukup membaca data dari memory store Redis, sehingga waktu respon menjadi sangat kecil.

## Apa Keuntungan Caching?

- Mengurangi response time
- Mengurangi beban ke external API
- Mengurangi jumlah request berulang untuk data yang sama
- Meningkatkan pengalaman pengguna karena respon lebih cepat

## Kapan Sebaiknya Tidak Menggunakan Cache?

- Saat data harus selalu real-time dan tidak boleh stale
- Saat data sangat sering berubah
- Saat hasil request bersifat sangat personal atau sensitif dan tidak aman jika dibagikan
- Saat biaya invalidasi cache lebih besar daripada manfaat performanya

## Catatan Expiry 5 Menit

Mahasiswa tidak perlu menunggu 5 menit saat demo. Cukup jelaskan bahwa setelah `TTL` habis, Redis akan menghapus key, sehingga pemanggilan berikutnya menjadi lambat lagi karena aplikasi harus mengambil data dari sumber API terlebih dahulu.
