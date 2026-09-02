Feature: Integration Tests

 Background:
 * def contextPath = '/cccodr'
 * def rootUrl = urlBase + contextPath + '/'

 Scenario: Root endpoint integration test
 Given url rootUrl
 When method get
 Then status 200
 And match response.message contains 'Hello'
