# coverity-commit-checker
Will check is Coverity commit needed by using Coverity Connect REST API. This action can be used to check that is the full commit from analysis engine to Coverity Connect needed. It can be used also to check is the emit percentage good enough, it can be used to notify developer team via Microsoft Teams about new finding or low emit percentage. Results will be tested against the latest snapshot of the given project stream or you can use Coverity Connect Views as well.

## Available Options
| Option name | Description | Default value | Required |
|----------|----------|---------|----------|
| project | Project name in Coverity Connect | - | true |
| stream | Project stream name in Coverity Connect | - | true |
| cov_username | Coverity Connect username | - | true |
| cov_password | Coverity Connect password | - | true |
| cov_url | URL for Coverity Connect | - | true |
| cov_install_folder | Where Coverity tools are installed. If not given, then expects tools to be in runner PATH | - | false |
| intermediate_dir | Intermediate directory | - | true |
| log_level | Logging level | DEBUG | false |
| teams_webhook_url | Microsoft Teams WebHook URL. By giving this, the Teams notification is activated | - | false |
| force_commit | Setting this true, it will do the commit and will not do any checkings. | false | false |
| dryrun | Set this true, if you want to run tests and not to do the commit. | false | false |
| break_build | Set this true, if you want to break the build, if there are new findings. | false | false |
| emit_threshold | With this you can set the emit threshold percentage, the default is 95 | 95 | false |
| viewID | ID or the name of that view which result is used to get findings | - | false |

## Usage

**Example usage**
```yaml
    - name: Coverity Commit phase
      uses: lejouni/coverity-commit-checker@v5.6.5
      with:
        project: test-project
        stream: test-project-main
        cov_username: ${{secrets.COVERITY_USERNAME}} #Coverity Connect username
        cov_password: ${{secrets.COVERITY_ACCESS_TOKEN}} #Coverity Connect password
        cov_url: ${{secrets.COVERITY_SERVER_URL}} #Coverity Connect server URL
        intermediate_dir: ${{github.workspace}}/idir
        log_level: INFO
        teams_webhook_url: ${{secrets.TEAMS_WEBHOOK}}
        force_commit: false
        dryrun: false
        break_build: false
        emit_threshold: 95
        viewID: testView
```
