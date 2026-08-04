package aiverify.discovery.systemui

import aiverify.discovery.weather.WeatherProvider

interface UiRenderer {
    fun render(summary: String)
}
class SystemUiWeatherConsumer(
    private val provider: WeatherProvider,
    private val renderer: UiRenderer,
) {
    fun refresh() {
        val weather = provider.current()
        renderer.render(weather.summary)
    }
}
