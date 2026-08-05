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

        // M7-R1 binds the frozen WeatherService delay input to a build-time
        // resource.  The matched control uses zero; the defect build passes
        // -PtemporalDelayMs=250.  The Android adapter remains identical.
        val temporalDelayMs = project.providers.gradleProperty("temporalDelayMs").orElse("0").get()
        require(temporalDelayMs.toIntOrNull()?.let { it >= 0 } == true) {
            "temporalDelayMs must be a non-negative integer"
        }
        resValue("integer", "temporal_delay_ms", temporalDelayMs)
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = false
        resValues = true
    }
}
