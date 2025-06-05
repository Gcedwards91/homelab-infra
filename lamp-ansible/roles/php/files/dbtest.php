<?php
$servername = "alma-db-01";
$username = "webuser";
$password = "webpass";
$dbname = "appdb";

$conn = new mysqli($servername, $username, $password, $dbname);

if ($conn->connect_error) {
  die("Connection failed: " . $conn->connect_error);
}
echo "Connected successfully to MariaDB!";
$conn->close();
?>
