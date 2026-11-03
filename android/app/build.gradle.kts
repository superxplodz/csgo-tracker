plugins { id("com.android.application") }

android {
    namespace = "id.my.bekasibro.skins"
    compileSdk = 34
    defaultConfig {
        applicationId = "id.my.bekasibro.skins"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
