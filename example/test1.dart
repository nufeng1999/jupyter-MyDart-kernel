

import 'package:args/args.dart';
void main(List<String> args){
    var parser = ArgParser();
    parser.addOption('mode');
    parser.addFlag('verbose', defaultsTo: true);
    var results = parser.parse(args);

    print('${results['mode']}\n'); // debug
    print('${results['verbose']}\n'); // true
    
    
    for (var i = 0; i < 4; i++) {
        print("---------");
        print('hello $i');
    }


}
