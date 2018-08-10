<!DOCTYPE HTML>
<html>
<head>
    <title>Magpie admin area</title>
    <meta charset="UTF-8">
    <link rel="stylesheet" type="text/css" href="//fonts.googleapis.com/css?family=Open+Sans" />
    <link rel="shortcut icon" type="image/x-icon" href="${request.static_url('magpie.ui.home:static/settings.png')}" />
    <link href="${request.static_url('magpie.ui.home:static/style.css')}" rel="stylesheet" type="text/css" media="all" />
    <script type="text/javascript" src="https://ajax.googleapis.com/ajax/libs/jquery/1.5.2/jquery.min.js"></script>
    <style>
        <%block name="style"/>
    </style>
</head>
<body>

<div class="header">
    <a href="${request.route_url('home')}">
        <img src="${request.static_url('magpie.ui.home:static/settings_white.png')}">
        Magpie Administration
    </a>
    %if MAGPIE_LOGGED_USER:
        <button class="img_button" type="button" onclick="location.href='${request.route_url('logout')}'">Log out<br/>(${MAGPIE_LOGGED_USER})</button>
    %else:
        <button class="img_button" type="button" onclick="location.href='${request.route_url('login')}'">Log In</button>
    %endif
    <div class="clear"></div>
    <ul class="breadcrumb">
        <%block name="breadcrumb"/>
    </ul>
</div>

<div class="content">
${self.body()}
</div>

</body>
</html>

<script type="text/javascript">
    <%block name="script"/>
</script>
