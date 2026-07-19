plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "dev.aiverify.lifecyclefixture"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.aiverify.lifecyclefixture"
        minSdk = 23
        targetSdk = 35
        versionCode = 2
        versionName = "2.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = false
    }
}
