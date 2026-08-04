package aiverify.discovery.weather

data class Weather(val summary: String)

interface WeatherProvider {
    fun current(): Weather
}
class WeatherService : WeatherProvider {
    override fun current(): Weather = Weather(summary = "fixture-data")
}
