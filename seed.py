"""Konten awal untuk peninjauan. Bukan berita atau standar layanan resmi."""
LOGO_URL = 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Logo_Kementerian_Kebudayaan_Republik_Indonesia_%282024%29.svg/330px-Logo_Kementerian_Kebudayaan_Republik_Indonesia_%282024%29.svg.png'
SETTINGS = {
 'site_name':'Balai Pelestarian Kebudayaan Kaltim',
 'tagline':'Merawat warisan. Menghidupkan kebudayaan.',
 'hero_title':'Merawat warisan.\nMenghidupkan kebudayaan.',
 'hero_description':'Ruang bersama untuk mengenal, menjaga, dan mengembangkan kebudayaan Kalimantan Timur. Temukan cerita, jelajahi warisan, dan terhubung melalui layanan kebudayaan.',
 'logo_url':LOGO_URL, 'hero_image':'',
 'primary_color':'#5B3629','accent_color':'#C69A58','background_color':'#FAF7F2',
 'email':'','phone':'','address':'','office_hours':'',
 'instagram_url':'','youtube_url':'','maps_url':'','wbs_url':'',
 'about':'Balai Pelestarian Kebudayaan Kaltim hadir dalam rancangan portal ini sebagai ruang informasi, dokumentasi, dan layanan kebudayaan untuk masyarakat Kalimantan Timur. Website menghubungkan pengetahuan tentang warisan budaya, pelaku kebudayaan, dan akses pelayanan dalam satu tempat.\n\nNaskah profil, sejarah, visi dan misi, serta struktur organisasi dapat diisi dan disahkan pengelola melalui panel admin sebelum peluncuran resmi.',
 'history':'Halaman sejarah disiapkan untuk memuat lintasan kelembagaan balai. Pengelola dapat menambahkan uraian yang bersumber dari arsip, keputusan, dan dokumen resmi melalui Pengaturan Identitas.',
 'vision':'Naskah visi dan misi resmi dapat dimasukkan melalui panel admin setelah mendapatkan pengesahan balai.',
 'organization':'Struktur organisasi dan nama pejabat akan ditampilkan setelah diisi pengelola. Tidak ada nama pejabat atau susunan organisasi rekaan dalam data awal.',
 'privacy_text':'Data nama, alamat email, nomor kontak, uraian, dan lampiran digunakan untuk memproses permohonan. Jangan mengunggah NIK, kata sandi, atau data pribadi yang tidak diperlukan. Nomor tiket dan kunci lacak bersifat rahasia. Hanya pengelola yang berwenang dapat mengakses lampiran permohonan. Kebijakan retensi dan kontak penanggung jawab data perlu ditetapkan balai sebelum portal diluncurkan.',
 'review_mode':True,
}
SERVICE_SPECS = [
 ('Kajian Identifikasi Objek','Penelaahan awal terhadap objek yang diduga memiliki nilai kebudayaan.','landmark'),
 ('Pendampingan Rehabilitasi CB dan ODCB','Permohonan pendampingan dalam penanganan dan perawatan objek cagar budaya.','shield'),
 ('Fasilitasi Pemanfaatan CB dan ODCB','Konsultasi pemanfaatan objek dengan tetap memperhatikan pelestariannya.','leaf'),
 ('Edukasi Kebudayaan','Ruang belajar kebudayaan untuk sekolah, komunitas, dan masyarakat.','book'),
 ('Narasumber / Tenaga Ahli','Permohonan narasumber untuk kegiatan yang berkaitan dengan kebudayaan.','users'),
 ('Magang / Praktik Kerja','Pengajuan kegiatan belajar dan praktik kerja di lingkungan balai.','briefcase'),
 ('Identifikasi Lokasi di Kawasan Cagar Budaya Kaltim','Permohonan identifikasi lokasi yang berkaitan dengan kawasan cagar budaya di Kalimantan Timur.','map'),
 ('Penanganan Temuan / Kasus ODCB, CB, dan OPK','Penyampaian informasi temuan atau kasus terkait objek kebudayaan.','search'),
 ('Advokasi Penghayat Kepercayaan dan Masyarakat Adat','Permohonan fasilitasi komunikasi dan pendampingan kebudayaan.','heart'),
 ('Perpustakaan','Akses informasi koleksi, bahan bacaan, dan referensi kebudayaan.','library'),
 ('Pengaduan Masyarakat','Sampaikan masukan, keluhan, atau kendala pelayanan secara tertulis.','message'),
 ('Pemanfaatan Ruang Serbaguna','Pengajuan penggunaan ruang untuk kegiatan kebudayaan; ketersediaan dikonfirmasi pengelola.','building'),
 ('Permohonan Data dan Informasi','Permohonan informasi publik dan bahan dokumentasi kebudayaan.','file'),
 ('Cinebudaya','Film, cerita, dan dialog kebudayaan. Ajukan pemutaran, diskusi, atau usulan karya.','film'),
]
SERVICES = []
for i,(title,desc,icon) in enumerate(SERVICE_SPECS,1):
 SERVICES.append({'id':i,'title':title,'description':desc,'icon':icon,'active':True,'requirements':'Nama dan kontak pemohon\nUraian tujuan dan kebutuhan\nSurat atau bahan pendukung bila relevan','procedure':'Isi formulir permohonan\nSimpan nomor tiket dan kunci lacak\nPengelola memeriksa dan menindaklanjuti permohonan\nPantau tanggapan melalui menu Lacak Permohonan','time_note':'Jangka waktu dan ketentuan resmi dikonfirmasi oleh pengelola.','fee_note':'Informasi biaya mengikuti standar layanan yang disahkan balai.','standard_note':'Rancangan layanan diadaptasi dari referensi; bukan standar pelayanan resmi Kaltim.','source':'https://budayajatim.com/layanan/','sort_order':i})

POSTS = [
 {'id':1,'kind':'berita','category':'Ruang Budaya','title':'Mendokumentasikan cerita, menjaga ingatan bersama','excerpt':'Cerita keluarga, foto lama, dan pengetahuan lokal dapat menjadi awal percakapan tentang pelestarian.','body':'Kebudayaan juga hidup dalam cerita yang dituturkan dari satu generasi ke generasi berikutnya. Dokumentasi dapat dimulai dengan mencatat nama penutur, tempat, waktu, dan konteks cerita.\n\nMintalah persetujuan sebelum merekam atau menyebarluaskan cerita. Hormati bagian pengetahuan yang tidak boleh dipublikasikan, terutama pengetahuan yang memiliki batas akses dalam komunitas.\n\nKonten contoh ini memperlihatkan format artikel. Pengelola dapat menggantinya dengan tulisan yang telah ditinjau, dilengkapi sumber, dan memperoleh izin publikasi.','image':'','source':'','is_demo':True},
 {'id':2,'kind':'berita','category':'Pelestarian','title':'Mengenal warisan budaya, mulai dari sekitar kita','excerpt':'Ruang belajar untuk membaca kembali jejak kebudayaan di lingkungan sehari-hari.','body':'Warisan budaya dapat menjadi pintu masuk untuk memahami pengalaman masyarakat. Foto, arsip, bangunan, keterampilan, dan praktik yang diwariskan memerlukan penjelasan konteks yang hati-hati.\n\nDokumentasi objek tidak dengan sendirinya berarti penetapan sebagai cagar budaya. Status hukum setiap objek harus dijelaskan berdasarkan dokumen yang sah.\n\nIni merupakan konten contoh, bukan pengumuman penetapan objek atau laporan kegiatan balai.','image':'','source':'','is_demo':True},
 {'id':3,'kind':'pengumuman','category':'Informasi Portal','title':'Selamat datang di rumah digital kebudayaan Kaltim','excerpt':'Kenali menu layanan, dokumentasi, dan Cinebudaya dalam rancangan portal yang dapat dikelola secara mandiri.','body':'Portal ini menyediakan menu profil, layanan, entitas kebudayaan, PPID, SAKIP, peraturan, publikasi, agenda, dan Cinebudaya.\n\nPada tahap peninjauan, semua pengajuan adalah data uji. Pengelola harus mengesahkan identitas dan standar layanan sebelum digunakan oleh masyarakat.','image':'','source':'','is_demo':True},
 {'id':4,'kind':'entitas','category':'Dokumentasi Budaya','title':'Ruang arsip dan jejak kebudayaan','excerpt':'Format dokumentasi objek, lokasi, sumber, dan riwayat pelestarian dalam satu halaman.','body':'Gunakan halaman ini untuk mendokumentasikan objek kebudayaan. Lengkapi nama objek, lokasi, uraian, sumber, kredit foto, dan informasi status hukumnya.\n\nEntri ini adalah contoh struktur dokumentasi, bukan pencatatan resmi atau penetapan cagar budaya.','image':'','location':'Kalimantan Timur','is_demo':True},
 {'id':5,'kind':'entitas','category':'Pengetahuan Lokal','title':'Cerita yang hidup di tengah masyarakat','excerpt':'Ruang untuk dokumentasi tradisi, pengetahuan, dan penuturan yang dibagikan dengan persetujuan.','body':'Sertakan nama komunitas atau penutur hanya apabila mereka menyetujui publikasinya. Tuliskan konteks dan batas penggunaan dokumentasi.\n\nKonten contoh ini dapat diganti dengan hasil pendokumentasian yang telah diverifikasi.','location':'Kalimantan Timur','is_demo':True},
 {'id':6,'kind':'cinebudaya','category':'Film','title':'Kaltim dalam bingkai cerita','excerpt':'Ruang pemutaran dokumenter dan karya audiovisual kebudayaan.','body':'Tambahkan tautan YouTube, Vimeo, atau berkas MP4 berizin melalui panel admin untuk mengaktifkan pemutar. Lengkapi sinopsis, pembuat, tahun produksi, dan hak tayang.\n\nIni adalah kartu contoh; tidak ada film rekaan yang dinyatakan sebagai produksi resmi balai.','video_url':'','duration':'','is_demo':True},
 {'id':7,'kind':'cinebudaya','category':'Cerita','title':'Ingatan yang dituturkan','excerpt':'Membaca cerita kebudayaan dan pengalaman yang dibagikan antargenerasi.','body':'Setiap cerita perlu didengarkan bersama konteksnya. Ruang Cerita dalam Cinebudaya dapat memuat esai, transkrip penuturan, atau catatan dokumentasi yang telah disunting dan diizinkan untuk terbit.\n\nPengelola dapat menambahkan nama penulis, sumber, foto, dan tautan audiovisual yang berkaitan. Ini adalah konten contoh untuk peninjauan.','video_url':'','is_demo':True},
 {'id':8,'kind':'cinebudaya','category':'Dialog','title':'Bertemu, mendengar, bertukar gagasan','excerpt':'Ruang percakapan tentang pelestarian dan masa depan kebudayaan.','body':'Kategori Dialog disiapkan untuk rekaman percakapan, rangkuman diskusi, dan dokumentasi pertemuan kebudayaan.\n\nLengkapi identitas narasumber atas persetujuan mereka, waktu kegiatan yang benar, sinopsis, dan rekaman berizin sebelum memublikasikan. Konten ini bukan laporan kegiatan nyata.','video_url':'','is_demo':True},
 {'id':9,'kind':'publikasi','category':'Panduan Portal','title':'Panduan singkat menggunakan layanan digital','excerpt':'Mengajukan permohonan, menyimpan kunci lacak, dan membaca tindak lanjut.','body':'Pilih jenis layanan. Lengkapi nama, email, nomor kontak, dan tujuan permohonan. Lampiran PDF atau gambar bersifat opsional.\n\nSimpan nomor tiket dan kunci lacak yang diberikan setelah pengajuan. Keduanya diperlukan untuk membaca status dan tanggapan pengelola.\n\nPada mode peninjauan, jangan gunakan data pribadi nyata.','is_demo':True},
]
for p in POSTS:
 for key,value in {'category':'','excerpt':'','body':'','image':'','attachment':'','video_url':'','duration':'','location':'','event_date':'','source':'','credit':'','status':'published','is_demo':True,'created_at':'2026-09-18T08:00:00+08:00','updated_at':'2026-09-18T08:00:00+08:00'}.items():p.setdefault(key,value)
