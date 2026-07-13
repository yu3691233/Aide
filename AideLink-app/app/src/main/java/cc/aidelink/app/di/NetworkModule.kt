package cc.aidelink.app.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.data.config.BridgeDefaults
import cc.aidelink.app.data.api.OpenCodeApi
import cc.aidelink.app.data.repository.SettingsRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "aidelink_prefs")

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        prettyPrint = false
        isLenient = true
        ignoreUnknownKeys = true
        coerceInputValues = true
        encodeDefaults = true
        explicitNulls = false
    }

    @Provides
    @Singleton
    fun provideHttpClient(json: Json): HttpClient = HttpClient(OkHttp) {
        install(ContentNegotiation) {
            json(json)
        }

        install(Logging) {
            level = LogLevel.INFO
        }

        install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 5_000
            socketTimeoutMillis = 30_000
        }

        install(WebSockets)

        engine {
            config {
                retryOnConnectionFailure(true)
            }
        }
    }

    @Provides
    @Singleton
    fun provideDataStore(@ApplicationContext context: Context): DataStore<Preferences> {
        return context.dataStore
    }

    @Provides
    @Singleton
    fun provideBridgeApi(): BridgeApi {
        return BridgeApi(baseUrl = BridgeDefaults.DEFAULT_BRIDGE_URL, authToken = null) // DI 初始值，由 ConnectionService 覆盖
    }

    @Provides
    @Singleton
    fun provideOpenCodeApi(httpClient: HttpClient, json: Json): OpenCodeApi {
        return OpenCodeApi(httpClient, json)
    }
}
